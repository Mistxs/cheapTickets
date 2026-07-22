


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




$(function() {

  rome(start_date, {
	  time: false,
      weekStart: 1,
      // inputFormat: 'YYYY-MM-DD'
      inputFormat: 'DD-MM-YYYY'
	});

	rome(end_date, {
	  time: false,
      weekStart: 1,
     // inputFormat: 'YYYY-MM-DD'
     inputFormat: 'DD-MM-YYYY'
	});
});

