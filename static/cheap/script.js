function setSearchProgress(pct) {
    var width = Math.max(0, Math.min(100, Number(pct) || 0)) + '%';
    $('#progress').width(width);
    var dockBar = document.getElementById('ct-topbar-progress-bar');
    if (dockBar) dockBar.style.width = width;
    updateDockedProgressVisibility();
}

function updateDockedProgressVisibility() {
    var dock = document.getElementById('ct-topbar-progress');
    var formProgress = document.querySelector('.mainform .progress');
    if (!dock || !formProgress) return;

    var searching = formProgress.style.display !== 'none' &&
        window.getComputedStyle(formProgress).display !== 'none';
    if (!searching) {
        dock.hidden = true;
        dock.setAttribute('aria-hidden', 'true');
        return;
    }

    var rect = formProgress.getBoundingClientRect();
    var topbar = document.querySelector('.ct-topbar');
    var topbarBottom = topbar ? topbar.getBoundingClientRect().bottom : 0;
    var visible = rect.bottom > topbarBottom + 4 && rect.top < window.innerHeight - 4;
    dock.hidden = visible;
    dock.setAttribute('aria-hidden', visible ? 'true' : 'false');
}

function startSearchProgress() {
    setSearchProgress(0);
    $('.progress').show();
    updateDockedProgressVisibility();
}

function stopSearchProgress() {
    $('.progress').hide();
    setSearchProgress(0);
    var dock = document.getElementById('ct-topbar-progress');
    if (dock) {
        dock.hidden = true;
        dock.setAttribute('aria-hidden', 'true');
    }
}

$(document).ready(function() {
    $('.progress').hide();
    $('.resrow').hide();
    window.globalData = null;

    window.addEventListener('scroll', updateDockedProgressVisibility, { passive: true });
    window.addEventListener('resize', updateDockedProgressVisibility);

    $('#search_button').on('click', function() {
    var start_date = $('#start_date').val();
    var end_date = $('#end_date').val();
    var city1Id = $('#city1-input').attr('data-city-id');
    var city2Id = $('#city2-input').attr('data-city-id');

    var wagonTypeSelector = document.getElementById('wagonTypeSelector');
    var selectedWagonType = wagonTypeSelector.value;

    startSearchProgress();

    $('#oldres tbody').empty();

    fetch(`/predata?start_date=${start_date}&end_date=${end_date}&city1=${city1Id}&city2=${city2Id}`)
        .then(response => response.json())
        .then(initialData => {
            displayResults(initialData, selectedWagonType);
            $('.resrow').show();
            document.getElementById("calendar").scrollIntoView({ behavior: "smooth" });

            var eventSource = new EventSource(`/search?start_date=${start_date}&end_date=${end_date}&city1=${city1Id}&city2=${city2Id}`, { withCredentials: true });

            eventSource.onmessage = function(event) {
                var response = JSON.parse(event.data);
                var progress = response.progress;
                setSearchProgress(progress);

                if (progress === 100) {
                    eventSource.close();
                    stopSearchProgress();
                                    var data = response.data;
                displayResults(data, selectedWagonType);
                }
            };
        });
});



    initCityAutocomplete($('.city-input'));
    initStyledSelects();
    initSubscriptionsUI();
});

function initCityAutocomplete($inputs) {
    $inputs.each(function() {
        var $el = $(this);
        if ($el.data('ui-autocomplete')) {
            $el.autocomplete('destroy');
        }
    });
    $inputs.autocomplete({
        appendTo: 'body',
        source: function (request, response) {
            $.ajax({
                url: '/autocomplete',
                data: { search: request.term },
                dataType: 'json',
                success: function (data) {
                    response(data);
                }
            });
        },
        minLength: 2,
        select: function(event, ui) {
            $(this).val(ui.item.label);
            $(this).attr('data-city-id', ui.item.value);
            return false;
        }
    });
}

function refreshSelectMenu($el) {
    if ($el && $el.length && $el.data('ui-selectmenu')) {
        $el.selectmenu('refresh');
    }
}

function setSelectValue($el, value) {
    $el.val(value);
    refreshSelectMenu($el);
}

function initStyledSelects() {
    $('#wagonTypeSelector, #sub-car-type, #sub-place-type').each(function() {
        var $el = $(this);
        if ($el.data('ui-selectmenu')) {
            $el.selectmenu('destroy');
        }
        var options = {
            appendTo: 'body',
            width: null,
            classes: {
                'ui-selectmenu-button': 'ct-select-button',
                'ui-selectmenu-menu': 'ct-select-menu'
            },
            position: {
                my: 'left top+4',
                at: 'left bottom',
                collision: 'flipfit'
            }
        };
        if ($el.attr('id') === 'wagonTypeSelector') {
            options.change = function() {
                onChangeWagonType();
            };
        }
        $el.selectmenu(options);
    });
}

function pad2(n) {
    return String(n).padStart(2, '0');
}

function formatDmy(date) {
    return pad2(date.getDate()) + '-' + pad2(date.getMonth() + 1) + '-' + date.getFullYear();
}

function dmyTodayPlus(days) {
    var d = new Date();
    d.setDate(d.getDate() + days);
    return formatDmy(d);
}

function dmyToIso(dmy) {
    if (!dmy) return '';
    var parts = String(dmy).trim().split('-');
    if (parts.length !== 3) return '';
    if (parts[0].length === 4) {
        return parts[0] + '-' + parts[1] + '-' + parts[2];
    }
    return parts[2] + '-' + parts[1] + '-' + parts[0];
}

function isoToDmy(iso) {
    if (!iso) return '';
    var parts = String(iso).trim().split('-');
    if (parts.length !== 3) return iso;
    if (parts[0].length === 4) {
        return parts[2] + '-' + parts[1] + '-' + parts[0];
    }
    return iso;
}

function normalizeTgNick(raw) {
    var value = String(raw || '').trim();
    if (!value) return '';
    if (value.charAt(0) !== '@') {
        value = '@' + value.replace(/^@+/, '');
    }
    return value;
}

function getStoredTgNick() {
    return localStorage.getItem('tg_id') || '';
}

function storeTgNick(nick) {
    nick = normalizeTgNick(nick);
    if (nick) {
        localStorage.setItem('tg_id', nick);
    }
    return nick;
}

function setSubDateValue(inputId, dmyValue) {
    var el = document.getElementById(inputId);
    if (!el) return;
    el.value = dmyValue || '';
    if (typeof rome !== 'undefined') {
        var existing = rome.find(el);
        if (existing) {
            existing.destroy();
        }
        if (typeof setupRomeRussianLocale === 'function') {
            setupRomeRussianLocale();
        } else if (rome.moment) {
            rome.moment.locale('ru');
        }
        var opts = Object.assign({}, window.CT_ROME_OPTS || {
            time: false,
            weekStart: 1,
            inputFormat: 'DD-MM-YYYY',
            autoHideOnBlur: false,
            monthFormat: 'MMMM YYYY',
            weekdayFormat: 'min'
        }, {
            initialValue: dmyValue || undefined,
            appendTo: document.body
        });
        rome(el, opts);
    }
}

function syncPlaceTypeForCarType() {
    var carType = $('#sub-car-type').val();
    var $place = $('#sub-place-type');
    if (carType === 'СИД') {
        $place.val('any').prop('disabled', true);
    } else {
        $place.prop('disabled', false);
    }
    if ($place.data('ui-selectmenu')) {
        if (carType === 'СИД') {
            $place.selectmenu('disable');
        } else {
            $place.selectmenu('enable');
        }
        $place.selectmenu('refresh');
    }
}

function resetSubscriptionForm() {
    $('#sub-id').val('');
    $('#sub-city1')
        .val($('#city1-input').val() || '')
        .attr('data-city-id', $('#city1-input').attr('data-city-id') || '');
    $('#sub-city2')
        .val($('#city2-input').val() || '')
        .attr('data-city-id', $('#city2-input').attr('data-city-id') || '');
    $('#sub-car-type').val('ПЛАЦ');
    $('#sub-place-type').val('lower');
    refreshSelectMenu($('#sub-car-type'));
    syncPlaceTypeForCarType();
    $('#sub-price-min').val(0);
    $('#sub-price-max').val(3000);
    $('#sub-notify-from').val('08:00');
    $('#sub-notify-to').val('23:00');

    var dateFrom = $('#start_date').val() || dmyTodayPlus(1);
    var dateTo = $('#end_date').val() || dmyTodayPlus(14);
    setSubDateValue('sub-date-from', dateFrom);
    setSubDateValue('sub-date-to', dateTo);

    $('#sub-tg-id').val(normalizeTgNick(getStoredTgNick()));
    $('#sub-form-status').text('');
    $('#saveSubscriptionBtn').text('Отправить').show();
}

function fillSubscriptionForm(sub) {
    $('#sub-id').val(sub.id);
    $('#sub-city1').val(sub.dep_name || '').attr('data-city-id', sub.dep_station || '');
    $('#sub-city2').val(sub.arr_name || '').attr('data-city-id', sub.arr_station || '');
    setSelectValue($('#sub-car-type'), sub.car_type);
    setSelectValue($('#sub-place-type'), sub.place_type);
    syncPlaceTypeForCarType();
    $('#sub-price-min').val(sub.price_min);
    $('#sub-price-max').val(sub.price_max);
    setSubDateValue('sub-date-from', isoToDmy(sub.date_from));
    setSubDateValue('sub-date-to', isoToDmy(sub.date_to));
    $('#sub-notify-from').val((sub.notify_from || '08:00').slice(0, 5));
    $('#sub-notify-to').val((sub.notify_to || '23:00').slice(0, 5));
    $('#sub-tg-id').val(normalizeTgNick(sub.tg_id));
    $('#saveSubscriptionBtn').text('Сохранить').show();
    $('#sub-form-tab').tab('show');
}

function placeTypeLabel(value) {
    if (value === 'lower') return 'нижнее';
    if (value === 'upper') return 'верхнее';
    return 'любое';
}

function carTypeLabel(value) {
    if (value === 'ANY') return 'любой вагон';
    if (value === 'ПЛАЦ') return 'плацкарт';
    if (value === 'КУПЕ') return 'купе';
    if (value === 'СИД') return 'сидячее';
    return value || '';
}

function renderSubscriptions(list) {
    var $box = $('#subscriptionsList');
    if (!list.length) {
        $box.html('<p class="ct-modal__empty">Активных подписок нет</p>');
        return;
    }
    var html = list.map(function(sub) {
        return (
            '<article class="subscription-item">' +
              '<div class="subscription-item__route">' + (sub.dep_name || '') + ' → ' + (sub.arr_name || '') + '</div>' +
              '<div class="subscription-item__meta">' + carTypeLabel(sub.car_type) + ' · ' + placeTypeLabel(sub.place_type) +
                ' · ' + Math.round(sub.price_min) + '–' + Math.round(sub.price_max) + ' ₽</div>' +
              '<div class="subscription-item__meta">' + isoToDmy(sub.date_from) + ' — ' + isoToDmy(sub.date_to) + '</div>' +
              '<div class="subscription-item__meta">оповещения ' +
                (sub.notify_from || '08:00').slice(0, 5) + '–' + (sub.notify_to || '23:00').slice(0, 5) +
                ' МСК</div>' +
              '<div class="subscription-item__actions">' +
                '<button type="button" class="btn btn-sm btn-primary edit-sub" data-id="' + sub.id + '">Редактировать</button>' +
                '<button type="button" class="btn btn-sm btn-outline-danger delete-sub" data-id="' + sub.id + '">Удалить</button>' +
              '</div>' +
            '</article>'
        );
    }).join('');
    $box.html(html);
    $box.data('items', list);
}

function loadSubscriptions() {
    var nick = normalizeTgNick($('#sub-list-tg-id').val());
    if (!nick || nick === '@') {
        $('#subscriptionsList').html('<p class="text-danger mb-0">Укажите Telegram ник</p>');
        return;
    }
    storeTgNick(nick);
    $('#sub-list-tg-id').val(nick);
    $('#subscriptionsList').html('<p class="text-muted mb-0">Загрузка…</p>');
    fetch('/api/subscriptions?tg_id=' + encodeURIComponent(nick))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.error) {
                $('#subscriptionsList').html('<p class="text-danger mb-0">' + data.error + '</p>');
                return;
            }
            renderSubscriptions(data);
        })
        .catch(function() {
            $('#subscriptionsList').html('<p class="text-danger mb-0">Ошибка загрузки</p>');
        });
}

function collectSubscriptionPayload() {
    var nick = normalizeTgNick($('#sub-tg-id').val());
    var carType = $('#sub-car-type').val();
    var placeType = carType === 'СИД' ? 'any' : $('#sub-place-type').val();
    return {
        tg_id: nick,
        dep_station: $('#sub-city1').attr('data-city-id'),
        arr_station: $('#sub-city2').attr('data-city-id'),
        dep_name: ($('#sub-city1').val() || '').trim(),
        arr_name: ($('#sub-city2').val() || '').trim(),
        car_type: carType,
        place_type: placeType,
        price_min: $('#sub-price-min').val(),
        price_max: $('#sub-price-max').val(),
        date_from: dmyToIso($('#sub-date-from').val()),
        date_to: dmyToIso($('#sub-date-to').val()),
        notify_from: ($('#sub-notify-from').val() || '08:00').slice(0, 5),
        notify_to: ($('#sub-notify-to').val() || '23:00').slice(0, 5)
    };
}

function bindTgNickInput($input) {
    $input.on('blur', function() {
        var nick = normalizeTgNick($(this).val());
        if (nick && nick !== '@') {
            $(this).val(nick);
        }
    });
    $input.on('input', function() {
        var val = $(this).val();
        if (val && val.charAt(0) !== '@') {
            $(this).val('@' + val.replace(/^@+/, ''));
        }
    });
}

function initSubscriptionsUI() {
    bindTgNickInput($('#sub-tg-id'));
    bindTgNickInput($('#sub-list-tg-id'));
    $('#sub-list-tg-id').val(normalizeTgNick(getStoredTgNick()) || '');
    $('#sub-car-type').on('change', syncPlaceTypeForCarType);

    $('#openSubscribeModal').on('click', function() {
        resetSubscriptionForm();
        $('#sub-form-tab').tab('show');
        $('#subscribeModal').modal('show');
    });

    $('#openMySubscriptions').on('click', function() {
        var nick = normalizeTgNick(getStoredTgNick());
        $('#sub-list-tg-id').val(nick || '@');
        $('#subscribeModal').modal('show');
        $('#sub-list-tab').tab('show');
        if (nick && nick !== '@') {
            loadSubscriptions();
        }
    });

    $('#subscribeModal').on('shown.bs.modal', function() {
        initCityAutocomplete($('#sub-city1, #sub-city2'));
        refreshSelectMenu($('#sub-car-type'));
        refreshSelectMenu($('#sub-place-type'));
    });

    $('#sub-list-tab').on('shown.bs.tab', function() {
        $('#sub-list-tg-id').val(normalizeTgNick($('#sub-tg-id').val() || getStoredTgNick()) || '@');
        $('#saveSubscriptionBtn').hide();
    });

    $('#sub-form-tab').on('shown.bs.tab', function() {
        $('#saveSubscriptionBtn').show();
    });

    $('#loadSubscriptionsBtn').on('click', loadSubscriptions);

    $('#saveSubscriptionBtn').on('click', function() {
        var payload = collectSubscriptionPayload();
        if (!payload.tg_id || payload.tg_id === '@') {
            $('#sub-form-status').text('Укажите Telegram ник, например @nick');
            return;
        }
        if (!payload.dep_station || !payload.arr_station) {
            $('#sub-form-status').text('Выберите станции из подсказки');
            return;
        }
        if (!payload.date_from || !payload.date_to) {
            $('#sub-form-status').text('Укажите диапазон дат');
            return;
        }

        storeTgNick(payload.tg_id);
        $('#sub-tg-id').val(payload.tg_id);
        $('#sub-list-tg-id').val(payload.tg_id);
        $('#sub-form-status').text('Сохранение…');

        var subId = $('#sub-id').val();
        var url = subId ? '/api/subscriptions/' + subId : '/api/subscriptions';
        var method = subId ? 'PUT' : 'POST';

        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
        .then(function(res) {
            if (!res.ok) {
                $('#sub-form-status').text('Ошибка: ' + (res.data.details || res.data.error || 'validation'));
                return;
            }
            $('#sub-form-status').text('Подписка сохранена');
            resetSubscriptionForm();
            $('#sub-list-tab').tab('show');
            loadSubscriptions();
        })
        .catch(function() {
            $('#sub-form-status').text('Сетевая ошибка');
        });
    });

    $('#subscriptionsList').on('click', '.edit-sub', function() {
        var id = Number($(this).data('id'));
        var items = $('#subscriptionsList').data('items') || [];
        var sub = items.find(function(item) { return item.id === id; });
        if (sub) {
            fillSubscriptionForm(sub);
        }
    });

    var pendingDeleteId = null;

    function hideDeleteConfirm() {
        pendingDeleteId = null;
        $('#subDeleteConfirm').prop('hidden', true);
    }

    function showDeleteConfirm(id, sub) {
        pendingDeleteId = id;
        var label = sub
            ? ((sub.dep_name || '') + ' → ' + (sub.arr_name || ''))
            : ('#' + id);
        $('#subDeleteConfirmText').text('Удалить подписку «' + label + '»?');
        $('#subDeleteConfirm').prop('hidden', false);
    }

    $('#subDeleteCancelBtn').on('click', hideDeleteConfirm);

    $('#subDeleteConfirmBtn').on('click', function() {
        var id = pendingDeleteId;
        var nick = normalizeTgNick($('#sub-list-tg-id').val() || getStoredTgNick());
        if (!id || !nick || nick === '@') {
            hideDeleteConfirm();
            return;
        }
        $('#subDeleteConfirmBtn').prop('disabled', true).text('Удаление…');
        fetch('/api/subscriptions/' + id + '?tg_id=' + encodeURIComponent(nick), { method: 'DELETE' })
            .then(function(r) { return r.json().then(function(data) { return { ok: r.ok, data: data }; }); })
            .then(function(res) {
                hideDeleteConfirm();
                $('#subDeleteConfirmBtn').prop('disabled', false).text('Удалить');
                if (res.ok) {
                    loadSubscriptions();
                } else {
                    $('#subscriptionsList').prepend(
                        '<p class="text-danger mb-2">' + (res.data.error || 'Не удалось удалить') + '</p>'
                    );
                }
            })
            .catch(function() {
                hideDeleteConfirm();
                $('#subDeleteConfirmBtn').prop('disabled', false).text('Удалить');
            });
    });

    $('#subscriptionsList').on('click', '.delete-sub', function() {
        var id = Number($(this).data('id'));
        var nick = normalizeTgNick($('#sub-list-tg-id').val() || getStoredTgNick());
        if (!nick || nick === '@') {
            return;
        }
        var items = $('#subscriptionsList').data('items') || [];
        var sub = items.find(function(item) { return item.id === id; });
        showDeleteConfirm(id, sub);
    });

    $('#subscribeModal').on('hidden.bs.modal', hideDeleteConfirm);
}


// блядский календарь как мне он дорог
(function($) {

	"use strict";

	document.addEventListener('DOMContentLoaded', function(){
    var today = new Date(),
        year = today.getFullYear(),
        month = today.getMonth(),
        monthTag =["Январь","Февраль","Март","Апрель","Май","Июнь","Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"],
        day = today.getDate(),
        days = document.getElementsByTagName('td'),
        selectedDay,
        setDate,
        daysLen = days.length;

    function Calendar(selector, options) {
        this.options = options;
        this.draw();
    }

    Calendar.prototype.draw  = function() {
        this.drawDays();
        var that = this,
            reset = document.getElementById('reset'),
            pre = document.getElementsByClassName('pre-button'),
            next = document.getElementsByClassName('next-button');

            pre[0].addEventListener('click', function(){that.preMonth(); });
            next[0].addEventListener('click', function(){that.nextMonth(); });

        while(daysLen--) {
            days[daysLen].addEventListener('click', function(){that.clickDay(this); });
        }
    };



    Calendar.prototype.drawHeader = function(e, ticketInfo) {
    var headDay = document.getElementsByClassName('head-day');
    var headMonth = document.getElementsByClassName('head-month');
    var calMonth = document.getElementsByClassName('cal-month');
    var ticketInfoBlock = document.querySelector('.ticket-info');
    var selectedCell = document.querySelector('td.selected[data-ticket-type]'); // Находим выбранную ячейку с типом билета

    e ? headDay[0].innerHTML = e : headDay[0].innerHTML = day;
    headMonth[0].innerHTML = monthTag[month] + " - " + year;
    calMonth[0].innerHTML = monthTag[month] + "  " + year;

    if (ticketInfo) {
        var trainNumber = ticketInfo.train;
        var trainVagon = ticketInfo.vagon_type;
        var depstation = ticketInfo.depstation;
        var arrstation = ticketInfo.arrstation;
        var departureTime = ticketInfo.dep_normal;
        var arrivalTime = ticketInfo.arr_normal;

        ticketInfoBlock.innerHTML =
        "<span class = 'key'>Поезд: </span> <span class = 'value'> " + trainNumber + "</span>" +
        "<span class = 'key'>Вагон: </span> <span class = 'value'> " + trainVagon + "</span>" +
        "<span class = 'key'>Отправление: </span> <span class = 'value'> " + departureTime + "<span class = 'station'> " + depstation + " </span> </span>" +
        "<span class = 'key'>Прибытие: </span> <span class = 'value'> " + arrivalTime + "<span class = 'station'> " + arrstation + " </span> </span>" +
        "<span class='rzd-link-wrap'></span>";

        var city1Id = $('#city1-input').attr('data-city-id');
        var city2Id = $('#city2-input').attr('data-city-id');
        var linkDate = ticketInfo.departure || '';
        if (city1Id && city2Id && linkDate) {
            fetch('/api/rzd-link?city1=' + encodeURIComponent(city1Id) +
                  '&city2=' + encodeURIComponent(city2Id) +
                  '&date=' + encodeURIComponent(linkDate))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.url) return;
                    var wrap = ticketInfoBlock.querySelector('.rzd-link-wrap');
                    if (!wrap) return;
                    wrap.innerHTML = '<a class="rzd-link" href="' + data.url +
                        '" target="_blank" rel="noopener">Открыть на РЖД</a>';
                })
                .catch(function() {});
        }
    } else {
        ticketInfoBlock.textContent = "Выберите день для просмотра информации о билете.";
    }
};



    Calendar.prototype.drawDays = function() {
        var startDay = new Date(year, month, 0).getDay(),
            nDays = new Date(year, month + 1, 0).getDate(),
            n = startDay,
            prevMonthDays = new Date(year, month, 0).getDate();

        for(var k = 0; k < 42; k++) {
            days[k].innerHTML = '';
            days[k].id = '';
            days[k].className = '';
            days[k].removeAttribute('data-ticket-info');
            days[k].removeAttribute('data-ticket-type');
            days[k].setAttribute('data-visible_date', '');
        }

        for (var p = 0; p < startDay; p++) {
            var prevDayNum = prevMonthDays - startDay + p + 1;
            var prevSpan = document.createElement('span');
            prevSpan.className = 'day';
            prevSpan.textContent = prevDayNum;
            days[p].appendChild(prevSpan);
            days[p].id = 'disabled';
            days[p].className = 'adj-month adj-month--prev';
        }

        for (var i = 1; i <= nDays; i++) {
            var dayElement = document.createElement('span');
            dayElement.className = 'day';
            dayElement.textContent = i;
            days[n].appendChild(dayElement);
            days[n].setAttribute('data-visible_date', year + '-' + (month + 1).toString().padStart(2, '0') + '-' + i.toString().padStart(2, '0'));
            n++;
        }

        var nextDay = 1;
        for (var f = n; f < 42; f++) {
            var nextSpan = document.createElement('span');
            nextSpan.className = 'day';
            nextSpan.textContent = nextDay++;
            days[f].appendChild(nextSpan);
            days[f].id = 'disabled';
            days[f].className = 'adj-month adj-month--next';
        }

        for(var j = 0; j < 42; j++) {
            if(days[j].id !== 'disabled' && j === day + startDay - 1){
                if((this.options && (month === setDate.getMonth()) && (year === setDate.getFullYear())) || (!this.options && (month === today.getMonth())&&(year===today.getFullYear()))){
                    this.drawHeader(day);
                    days[j].id = "today";
                }
            }
            if(selectedDay){
                if((j === selectedDay.getDate() + startDay - 1)&&(month === selectedDay.getMonth())&&(year === selectedDay.getFullYear())){
                days[j].className = "selected";
                this.drawHeader(selectedDay.getDate());
                }
            }
        }
    };

    Calendar.prototype.clickDay = function(o) {
        if (o.id === 'disabled' || o.classList.contains('adj-month')) {
            return;
        }
        var selected = document.querySelector(".selected");
        if (selected) {
            selected.classList.remove("selected");
        }
        o.classList.add("selected");

        var dayNode = o.querySelector('.day');
        if (!dayNode) {
            return;
        }
        var dayText = dayNode.textContent;
        var rawTicket = o.getAttribute('data-ticket-info');
        var ticketInfo = null;
        if (rawTicket) {
            try {
                ticketInfo = JSON.parse(rawTicket);
            } catch (e) {
                ticketInfo = null;
            }
        }
        selectedDay = new Date(year, month, dayText);
        this.drawHeader(dayText, ticketInfo);
    };



    Calendar.prototype.preMonth = function() {
        if(month < 1){
            month = 11;
            year = year - 1;
        }else{
            month = month - 1;
        }
        this.drawHeader(1);
        this.animateMonthChange();
        this.drawDays();
        onChangeWagonType();

    };

    Calendar.prototype.nextMonth = function() {
        if(month >= 11){
            month = 0;
            year =  year + 1;
        }else{
            month = month + 1;
        }
        this.drawHeader(1);
        this.animateMonthChange();
        this.drawDays();
        onChangeWagonType();
    };

    Calendar.prototype.animateMonthChange = function() {
        var grid = document.querySelector('.ct-cal-grid');
        if (!grid) return;
        grid.classList.remove('ct-cal-grid--animate');
        void grid.offsetWidth;
        grid.classList.add('ct-cal-grid--animate');
    };

    var calendar = new Calendar();

}, false);

})(jQuery);




function displayResults(data, selectedWagonType) {
    window.globalData = data;
    var calendarTable = document.getElementById('calendar');
    var cells = calendarTable.querySelectorAll('td');

    for (var i = 0; i < cells.length; i++) {
        var cell = cells[i];
        var priceElement = cell.querySelector('.price');
        if (priceElement) {
            priceElement.textContent = '';
            priceElement.classList.remove('cheapper', 'most-cheapper', 'expensive');
        }
        cell.removeAttribute('data-ticket-info');
        cell.removeAttribute('data-ticket-type');
    }

    for (var date in data) {
        var dateInfo = data[date];
        var cell = calendarTable.querySelector('td[data-visible_date="' + date + '"]');

        if (cell) {
            var minPrice = Infinity;
            var priceFound = false;
            var ticketdata = '';

            for (var type in dateInfo) {
                if (type !== 'БАГАЖ') {
                    var typeInfo = dateInfo[type];
                    var price = typeInfo.price;


                    if ((selectedWagonType === 'Самый дешевый' || selectedWagonType === type) && price < minPrice) {
                        minPrice = price;
                        priceFound = true;
                        ticketdata = JSON.stringify(typeInfo);
                    }
                }
            }

            var priceElement = cell.querySelector('.price');
            if (!priceElement) {
                priceElement = document.createElement('span');
                priceElement.className = 'price';
                cell.appendChild(priceElement);
            }

            if (priceFound) {
                priceElement.textContent = minPrice;
                var ticketInfo = JSON.stringify(dateInfo);
                cell.setAttribute('data-ticket-info', ticketdata);
            }  else {

                priceElement.textContent = '';
                cell.removeAttribute('data-ticket-type');
            }

        }
    updatePriceClasses();
    }
}

function onChangeWagonType() {
    var selector = document.getElementById('wagonTypeSelector');
    if (!selector || !window.globalData) {
        return;
    }
    displayResults(window.globalData, selector.value);
}

function updatePriceClasses() {
  const priceElements = Array.from(document.querySelectorAll('#calendar .price'));
  const prices = priceElements
    .map(function(element) { return parseFloat(element.textContent); })
    .filter(function(price) { return !isNaN(price) && price > 0; });

  if (!prices.length) {
    priceElements.forEach(function(element) {
      element.classList.remove('cheapper', 'most-cheapper', 'expensive');
    });
    return;
  }

  const minPrice = Math.min.apply(null, prices);
  const averagePrice = prices.reduce(function(sum, price) { return sum + price; }, 0) / prices.length;

  priceElements.forEach(function(element) {
    const price = parseFloat(element.textContent);
    element.classList.remove('cheapper', 'most-cheapper', 'expensive');
    if (isNaN(price) || price <= 0) {
      return;
    }
    if (price === minPrice) {
      element.classList.add('cheapper');
    } else if (price < averagePrice) {
      element.classList.add('most-cheapper');
    } else if (price > averagePrice) {
      element.classList.add('expensive');
    }
  });
}