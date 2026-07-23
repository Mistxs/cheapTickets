"""CheapTickets /backoffice — Flask-Login admin panel."""
from __future__ import annotations

import os
import secrets
import subprocess
import threading
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path

import pymysql
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from cities import db_params
import applog
import tgbot

backoffice_bp = Blueprint("backoffice", __name__, url_prefix="/backoffice")

login_manager = LoginManager()
login_manager.login_view = "backoffice.login"
login_manager.login_message = "Нужна авторизация."

SYSTEMD_UNITS = (
    "cheaptickets.service",
    "cheaptickets-subs.service",
    "cheaptickets-bot.service",
)

LOG_SOURCES = {
    "rzd": "RZD API",
    "telegram": "Telegram API",
    "checker": "Checker",
    "journal:cheaptickets": "systemd: app",
    "journal:cheaptickets-subs": "systemd: subs",
    "journal:cheaptickets-bot": "systemd: bot",
}

PROJECT_ROOT = Path(__file__).resolve().parent


class AdminUser(UserMixin):
    def __init__(self, user_id="1", username="admin"):
        self.id = user_id
        self.username = username


@login_manager.user_loader
def load_user(user_id):
    expected = os.environ.get("BACKOFFICE_USER", "admin")
    if str(user_id) == "1":
        return AdminUser(username=expected)
    return None


def init_backoffice(app):
    """Call once after Flask app is created."""
    _load_env_file(PROJECT_ROOT / ".env.backoffice")
    secret = os.environ.get("SECRET_KEY") or os.environ.get("BACKOFFICE_SECRET_KEY")
    if not secret:
        secret = "dev-insecure-" + secrets.token_hex(8)
        app.logger.warning("SECRET_KEY not set — using ephemeral dev key")
    app.config["SECRET_KEY"] = secret
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    login_manager.init_app(app)
    app.register_blueprint(backoffice_bp)


def _load_env_file(path: Path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf"] = token
    return token


def _check_csrf():
    token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf"):
        abort(400, description="CSRF token missing or invalid")


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            _check_csrf()
        return view(*args, **kwargs)

    return wrapped


def _admin_credentials_ok(username: str, password: str) -> bool:
    expected_user = os.environ.get("BACKOFFICE_USER", "").strip()
    password_hash = os.environ.get("BACKOFFICE_PASSWORD_HASH", "").strip()
    if not expected_user or not password_hash:
        return False
    if username.strip() != expected_user:
        return False
    try:
        return check_password_hash(password_hash, password)
    except Exception:
        return False


def _db():
    return pymysql.connect(**db_params)


def _query_one(sql, args=None):
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchone()
    finally:
        conn.close()


def _query_all(sql, args=None):
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall() or []
    finally:
        conn.close()


def _execute(sql, args=None):
    conn = _db()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            conn.commit()
            return cur.rowcount
    finally:
        conn.close()


def _systemd_status(unit: str) -> dict:
    result = {
        "unit": unit,
        "active": "unknown",
        "sub": "unknown",
        "pid": None,
        "restarts": None,
        "since": None,
        "ok": False,
    }
    try:
        show = subprocess.run(
            [
                "systemctl",
                "show",
                unit,
                "--no-page",
                "-p",
                "ActiveState",
                "-p",
                "SubState",
                "-p",
                "MainPID",
                "-p",
                "NRestarts",
                "-p",
                "ActiveEnterTimestamp",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        props = {}
        for line in (show.stdout or "").splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                props[k] = v
        result["active"] = props.get("ActiveState", "unknown")
        result["sub"] = props.get("SubState", "unknown")
        result["pid"] = props.get("MainPID")
        result["restarts"] = props.get("NRestarts")
        result["since"] = props.get("ActiveEnterTimestamp") or None
        result["ok"] = result["active"] == "active"
    except Exception as exc:
        result["error"] = str(exc)
    return result


def _dashboard_metrics() -> dict:
    active = _query_one("SELECT COUNT(*) AS c FROM subscriptions WHERE active = 1")
    inactive = _query_one("SELECT COUNT(*) AS c FROM subscriptions WHERE active = 0")
    users = _query_one(
        "SELECT COUNT(DISTINCT LOWER(tg_id)) AS c FROM subscriptions WHERE active = 1"
    )
    since = datetime.now() - timedelta(hours=24)
    notified = _query_one(
        "SELECT COUNT(*) AS c FROM subscriptions WHERE last_notified_at >= %s",
        (since,),
    )
    top = _query_all(
        """
        SELECT dep_name, arr_name, COUNT(*) AS c
        FROM subscriptions
        WHERE active = 1
        GROUP BY dep_name, arr_name
        ORDER BY c DESC
        LIMIT 8
        """
    )
    return {
        "active": (active or {}).get("c", 0),
        "inactive": (inactive or {}).get("c", 0),
        "users": (users or {}).get("c", 0),
        "notified_24h": (notified or {}).get("c", 0),
        "top_routes": top,
    }


def _journal_tail(unit: str, lines: int = 100) -> str:
    lines = max(1, min(int(lines), 500))
    short = unit if unit.endswith(".service") else f"{unit}.service"
    if short not in SYSTEMD_UNITS:
        return "unit not allowed"
    try:
        proc = subprocess.run(
            ["journalctl", "-u", short, "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0 and not out:
            return err or f"journalctl exit {proc.returncode}"
        return out or "(пусто)"
    except Exception as exc:
        return f"(ошибка journalctl: {exc})"


def _read_log_source(source: str, lines: int = 200) -> str:
    if source in ("rzd", "telegram", "checker"):
        return applog.read_log_tail(source, lines)
    if source.startswith("journal:"):
        unit = source.split(":", 1)[1]
        return _journal_tail(unit, lines)
    return "unknown source"


def _run_checker_once():
    env = os.environ.copy()
    venv_python = PROJECT_ROOT / "venv" / "bin" / "python"
    python = str(venv_python if venv_python.exists() else "python3")
    script = str(PROJECT_ROOT / "pricesheduler.py")
    applog.checker_logger().info("manual checker start (from backoffice)")
    try:
        proc = subprocess.run(
            [python, script, "--once"],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        applog.checker_logger().info(
            "manual checker finished code=%s",
            proc.returncode,
        )
        if proc.stdout:
            for line in proc.stdout.splitlines()[-40:]:
                applog.checker_logger().info("out: %s", line)
        if proc.stderr:
            for line in proc.stderr.splitlines()[-20:]:
                applog.checker_logger().warning("err: %s", line)
    except Exception as exc:
        applog.checker_logger().exception("manual checker failed: %s", exc)


# --- views ---


@backoffice_bp.context_processor
def inject_globals():
    return {"csrf_token": _csrf_token, "bo_user": current_user}


@backoffice_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("backoffice.dashboard"))
    error = None
    if request.method == "POST":
        _check_csrf()
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if _admin_credentials_ok(username, password):
            login_user(AdminUser(username=username.strip()), remember=False)
            next_url = request.args.get("next") or url_for("backoffice.dashboard")
            if not next_url.startswith("/backoffice"):
                next_url = url_for("backoffice.dashboard")
            return redirect(next_url)
        error = "Неверный логин или пароль"
    return render_template("backoffice/login.html", error=error)


@backoffice_bp.route("/logout", methods=["POST"])
@login_required
@csrf_protect
def logout():
    logout_user()
    return redirect(url_for("backoffice.login"))


@backoffice_bp.route("/")
@login_required
def dashboard():
    metrics = _dashboard_metrics()
    services = [_systemd_status(u) for u in SYSTEMD_UNITS]
    return render_template(
        "backoffice/dashboard.html",
        metrics=metrics,
        services=services,
    )


@backoffice_bp.route("/api/run-checker", methods=["POST"])
@login_required
@csrf_protect
def run_checker():
    threading.Thread(target=_run_checker_once, daemon=True).start()
    flash("Чекер запущен в фоне. Смотри вкладку логов Checker.", "ok")
    return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/subscriptions")
@login_required
def subscriptions_list():
    tg_id = (request.args.get("tg_id") or "").strip().lstrip("@").lower()
    active = request.args.get("active", "")
    q = (request.args.get("q") or "").strip()

    sql = "SELECT * FROM subscriptions WHERE 1=1"
    args = []
    if tg_id:
        sql += " AND LOWER(tg_id) = %s"
        args.append(tg_id)
    if active in ("0", "1"):
        sql += " AND active = %s"
        args.append(int(active))
    if q:
        sql += " AND (dep_name LIKE %s OR arr_name LIKE %s)"
        args.extend([f"%{q}%", f"%{q}%"])
    sql += " ORDER BY id DESC LIMIT 500"
    rows = _query_all(sql, args)
    serialized = [tgbot.serialize_sub_row(r) for r in rows]
    # keep raw active/last_notified
    for i, r in enumerate(rows):
        serialized[i]["last_notified_at"] = r.get("last_notified_at")
        serialized[i]["created_at"] = r.get("created_at")
    return render_template(
        "backoffice/subscriptions.html",
        items=serialized,
        filters={"tg_id": tg_id, "active": active, "q": q},
    )


@backoffice_bp.route("/subscriptions/<int:sub_id>", methods=["GET", "POST"])
@login_required
def subscription_edit(sub_id):
    row = _query_one("SELECT * FROM subscriptions WHERE id = %s", (sub_id,))
    if not row:
        abort(404)
    if request.method == "POST":
        _check_csrf()
        action = request.form.get("action") or "save"
        if action == "delete":
            _execute("UPDATE subscriptions SET active = 0 WHERE id = %s", (sub_id,))
            flash(f"Подписка #{sub_id} деактивирована", "ok")
            return redirect(url_for("backoffice.subscriptions_list"))
        if action == "restore":
            _execute("UPDATE subscriptions SET active = 1 WHERE id = %s", (sub_id,))
            flash(f"Подписка #{sub_id} восстановлена", "ok")
            return redirect(url_for("backoffice.subscription_edit", sub_id=sub_id))

        try:
            price_min = float(request.form.get("price_min") or 0)
            price_max = float(request.form.get("price_max") or 0)
            date_from = datetime.strptime(request.form.get("date_from"), "%Y-%m-%d").date()
            date_to = datetime.strptime(request.form.get("date_to"), "%Y-%m-%d").date()
            notify_from = request.form.get("notify_from") or "08:00"
            notify_to = request.form.get("notify_to") or "23:00"
            car_type = (request.form.get("car_type") or "ANY").strip().upper()
            place_type = (request.form.get("place_type") or "any").strip().lower()
            active = 1 if request.form.get("active") == "1" else 0
            if car_type == "СИД":
                place_type = "any"
            if date_from > date_to:
                raise ValueError("date_from > date_to")
            if price_min > price_max:
                raise ValueError("price_min > price_max")
        except Exception as exc:
            flash(f"Ошибка валидации: {exc}", "err")
            return redirect(url_for("backoffice.subscription_edit", sub_id=sub_id))

        _execute(
            """
            UPDATE subscriptions SET
                price_min=%s, price_max=%s,
                date_from=%s, date_to=%s,
                notify_from=%s, notify_to=%s,
                car_type=%s, place_type=%s,
                active=%s,
                last_notify_signature=NULL
            WHERE id=%s
            """,
            (
                price_min,
                price_max,
                date_from,
                date_to,
                notify_from,
                notify_to,
                car_type,
                place_type,
                active,
                sub_id,
            ),
        )
        flash("Сохранено", "ok")
        if request.form.get("notify_tg") == "1":
            sub = tgbot.serialize_sub_row(
                _query_one("SELECT * FROM subscriptions WHERE id = %s", (sub_id,))
            )
            tgbot.notify_subscription_change(sub, action="updated")
            flash("Уведомление отправлено в Telegram", "ok")
        return redirect(url_for("backoffice.subscription_edit", sub_id=sub_id))

    sub = tgbot.serialize_sub_row(row)
    sub["last_notified_at"] = row.get("last_notified_at")
    sub["created_at"] = row.get("created_at")
    return render_template("backoffice/subscription_edit.html", sub=sub)


@backoffice_bp.route("/logs")
@login_required
def logs_page():
    source = request.args.get("source") or "checker"
    if source not in LOG_SOURCES:
        source = "checker"
    lines = request.args.get("lines") or "200"
    try:
        lines_n = int(lines)
    except ValueError:
        lines_n = 200
    body = _read_log_source(source, lines_n)
    return render_template(
        "backoffice/logs.html",
        sources=LOG_SOURCES,
        source=source,
        lines=lines_n,
        body=body,
    )
