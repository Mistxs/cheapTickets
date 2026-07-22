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

function isCtDateInput(el) {
  return !!(el && el.matches && el.matches(CT_DATE_SELECTOR));
}

function hideAllRomeCalendars() {
  if (typeof rome === 'undefined' || !rome.find) return;
  document.querySelectorAll(CT_DATE_SELECTOR).forEach(function(el) {
    var cal = rome.find(el);
    if (cal && cal.hide) cal.hide();
  });
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

  document.addEventListener('touchstart', function(e) {
    if (!e.touches || !e.touches.length) return;
    touchMoved = false;
    touchStartY = e.touches[0].clientY;
  }, { passive: true, capture: true });

  document.addEventListener('touchmove', function(e) {
    if (!e.touches || !e.touches.length) return;
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
    suppressUntil = Date.now() + 350;
    hideAllRomeCalendars();
  }, { passive: true });

  document.addEventListener('wheel', function() {
    suppressUntil = Date.now() + 350;
    hideAllRomeCalendars();
  }, { passive: true });
}


$(function() {
  var romeOpts = {
    time: false,
    weekStart: 1,
    inputFormat: 'DD-MM-YYYY'
  };

  if (typeof start_date !== 'undefined' && start_date) {
    rome(start_date, romeOpts);
  }
  if (typeof end_date !== 'undefined' && end_date) {
    rome(end_date, romeOpts);
  }

  initRomeDateGuards();
});
