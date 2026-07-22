  document.addEventListener("DOMContentLoaded", function() {
    const backgrounds = [
      "1.jpg",
      "2.jpg",
      "3.jpg",
      "4.jpg",
      "5.jpg",
      "6.jpg",
      "7.jpg",
      "8.jpg",
      "9.jpg",
      "10.jpg"
    ];

    function getRandomBackground() {
      const randomIndex = Math.floor(Math.random() * backgrounds.length);
      return backgrounds[randomIndex];
    }

    function optimizeBackgroundImage(imagePath) {
      const img = new Image();
      img.src = imagePath;
      img.onload = function() {
        const atmosphere = document.querySelector(".ct-atmosphere");
        if (atmosphere) {
          atmosphere.style.backgroundImage =
            "linear-gradient(165deg, rgba(11,17,23,0.82) 0%, rgba(14,20,27,0.72) 45%, rgba(14,20,27,0.88) 100%), " +
            "url('" + imagePath + "')";
          atmosphere.style.backgroundSize = "cover";
          atmosphere.style.backgroundPosition = "center";
        } else {
          document.body.style.backgroundImage = "url('" + imagePath + "')";
        }
      };
    }

    const randomBackground = getRandomBackground();
    optimizeBackgroundImage(`/cheaptickets/static/cheap/images/background/${randomBackground}`);
    document.body.classList.add("loaded");
  });


var CT_DATE_SELECTOR = '.ct-date-input, #start_date, #end_date, #sub-date-from, #sub-date-to';

window.CT_ROME_OPTS = {
  time: false,
  weekStart: 1,
  inputFormat: 'DD-MM-YYYY',
  monthFormat: 'MMMM YYYY',
  weekdayFormat: 'min',
  // Keep calendar open while switching months (month buttons steal focus otherwise)
  autoHideOnBlur: false
};

function isCtDateInput(el) {
  return !!(el && el.matches && el.matches(CT_DATE_SELECTOR));
}

function isInsideRomeCalendar(el) {
  return !!(el && el.closest && el.closest('.rd-container'));
}

function hideAllRomeCalendars() {
  if (typeof rome === 'undefined' || !rome.find) return;
  document.querySelectorAll(CT_DATE_SELECTOR).forEach(function(el) {
    var cal = rome.find(el);
    if (cal && cal.hide) cal.hide();
  });
}

function setupRomeRussianLocale() {
  if (typeof rome === 'undefined' || !rome.moment || !rome.moment.defineLocale) return;
  var m = rome.moment;
  var known = (m.locales && m.locales()) || [];
  if (known.indexOf('ru') === -1) {
    try {
      m.defineLocale('ru', {
        months: 'январь_февраль_март_апрель_май_июнь_июль_август_сентябрь_октябрь_ноябрь_декабрь'.split('_'),
        monthsShort: 'янв._февр._март_апр._май_июнь_июль_авг._сент._окт._нояб._дек.'.split('_'),
        weekdays: 'воскресенье_понедельник_вторник_среда_четверг_пятница_суббота'.split('_'),
        weekdaysShort: 'вс_пн_вт_ср_чт_пт_сб'.split('_'),
        weekdaysMin: 'вс_пн_вт_ср_чт_пт_сб'.split('_'),
        longDateFormat: {
          LT: 'HH:mm',
          LTS: 'HH:mm:ss',
          L: 'DD.MM.YYYY',
          LL: 'D MMMM YYYY',
          LLL: 'D MMMM YYYY HH:mm',
          LLLL: 'dddd, D MMMM YYYY HH:mm'
        },
        week: { dow: 1, doy: 4 }
      });
    } catch (err) {
      // locale already defined
    }
  }
  m.locale('ru');
}

function initRomeDateGuards() {
  var touchMoved = false;
  var touchStartY = 0;
  var suppressUntil = 0;

  function markScrollGesture() {
    touchMoved = true;
    suppressUntil = Date.now() + 450;
    hideAllRomeCalendars();
  }

  // Keep input focus when clicking month arrows / days — otherwise rome blurs and hides
  document.addEventListener('mousedown', function(e) {
    if (isInsideRomeCalendar(e.target)) {
      e.preventDefault();
    }
  }, true);

  document.addEventListener('touchstart', function(e) {
    if (!e.touches || !e.touches.length) return;
    if (isInsideRomeCalendar(e.target)) return;
    touchMoved = false;
    touchStartY = e.touches[0].clientY;
  }, { passive: true, capture: true });

  document.addEventListener('touchmove', function(e) {
    if (!e.touches || !e.touches.length) return;
    if (isInsideRomeCalendar(e.target)) return;
    if (Math.abs(e.touches[0].clientY - touchStartY) > 10) {
      markScrollGesture();
    }
  }, { passive: true, capture: true });

  // Rome opens on touchend — block that after a scroll gesture ends on a date field
  document.addEventListener('touchend', function(e) {
    if (!touchMoved && Date.now() >= suppressUntil) return;
    if (!isCtDateInput(e.target)) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    if (document.activeElement === e.target) {
      e.target.blur();
    }
  }, true);

  document.addEventListener('focusin', function(e) {
    if (!isCtDateInput(e.target)) return;
    if (touchMoved || Date.now() < suppressUntil) {
      e.target.blur();
      var cal = typeof rome !== 'undefined' && rome.find ? rome.find(e.target) : null;
      if (cal && cal.hide) cal.hide();
    }
  }, true);

  window.addEventListener('scroll', function() {
    if (document.activeElement && isInsideRomeCalendar(document.activeElement)) return;
    // Ignore scroll while a calendar is open and user is interacting with it
    var openCal = document.querySelector('.rd-container');
    if (openCal && openCal.style.display && openCal.style.display !== 'none') {
      // still close on page scroll away from search fields — but not on modal inner scroll alone
      // window scroll is fine to close search calendars
    }
    suppressUntil = Date.now() + 350;
    hideAllRomeCalendars();
  }, { passive: true });

  document.addEventListener('wheel', function(e) {
    if (isInsideRomeCalendar(e.target)) return;
    suppressUntil = Date.now() + 350;
    hideAllRomeCalendars();
  }, { passive: true });
}


$(function() {
  setupRomeRussianLocale();

  if (typeof start_date !== 'undefined' && start_date) {
    rome(start_date, window.CT_ROME_OPTS);
  }
  if (typeof end_date !== 'undefined' && end_date) {
    rome(end_date, window.CT_ROME_OPTS);
  }

  initRomeDateGuards();
});
