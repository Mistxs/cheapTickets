


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

    function optimizeBackgroundImage(imagePath, maxWidth) {
      const img = new Image();
      img.src = imagePath;

      img.onload = function() {
        // const aspectRatio = img.width / img.height;
        // const newWidth = Math.min(maxWidth, img.width);
        // const newHeight = newWidth / aspectRatio;

        document.body.style.backgroundImage = `url('${imagePath}')`;
        // document.body.style.backgroundSize = `${newWidth}px ${newHeight}px`;

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

