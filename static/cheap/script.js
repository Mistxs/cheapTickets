$(document).ready(function() {
    $('.progress').hide();
    $('.resrow').hide();
    var globalData = null;


    $('#search_button').on('click', function() {
    var start_date = $('#start_date').val();
    var end_date = $('#end_date').val();
    var city1Id = $('#city1-input').attr('data-city-id');
    var city2Id = $('#city2-input').attr('data-city-id');

    var wagonTypeSelector = document.getElementById('wagonTypeSelector');
    var selectedWagonType = wagonTypeSelector.value;

    $('.progress').show();

    $('#oldres tbody').empty();

    fetch(`cheaptickets/predata?start_date=${start_date}&end_date=${end_date}&city1=${city1Id}&city2=${city2Id}`)
        .then(response => response.json())
        .then(initialData => {
            displayResults(initialData, selectedWagonType);
            $('.resrow').show();
            document.getElementById("calendar").scrollIntoView({ behavior: "smooth" });

            var eventSource = new EventSource(`cheaptickets/search?start_date=${start_date}&end_date=${end_date}&city1=${city1Id}&city2=${city2Id}`, { withCredentials: true });

            eventSource.onmessage = function(event) {
                var response = JSON.parse(event.data);
                var progress = response.progress;
                $('#progress').width(progress + '%');


                if (progress === 100) {
                    eventSource.close();
                    $('.progress').hide();
                                    var data = response.data;
                displayResults(data, selectedWagonType);
                }
            };
        });
});



    $(function () {
            $(".city-input").autocomplete({
                source: function (request, response) {
                    $.ajax({
                        url: "cheaptickets/autocomplete",
                        data: { search: request.term },
                        dataType: "json",
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


        });

});


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
    var ticketInfoBlock = document.querySelector('.ticket-info');
    var selectedCell = document.querySelector('td.selected[data-ticket-type]'); // Находим выбранную ячейку с типом билета

    e ? headDay[0].innerHTML = e : headDay[0].innerHTML = day;
    headMonth[0].innerHTML = monthTag[month] + " - " + year;

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
        "<span class = 'key'>Прибытие: </span> <span class = 'value'> " + arrivalTime + "<span class = 'station'> " + arrstation + " </span> </span>"
    } else {
        ticketInfoBlock.textContent = "Выберите день для просмотра информации о билете.";
    }
};



    Calendar.prototype.drawDays = function() {
        var startDay = new Date(year, month, 0).getDay(),
            nDays = new Date(year, month + 1, 0).getDate(),
            n = startDay;

        // очистка всех дней нахрен
        for(var k = 0; k < 42; k++) {
            days[k].innerHTML = '';
            days[k].id = '';
            days[k].className = '';
            days[k].setAttribute('data-visible_date', ''); // Добавляем атрибут с пустым значением
        }

        for (var i = 1; i <= nDays; i++) {
            var dayElement = document.createElement('span');
            dayElement.className = 'day';
            dayElement.textContent = i;
            days[n].appendChild(dayElement);
            days[n].setAttribute('data-visible_date', year + '-' + (month + 1).toString().padStart(2, '0') + '-' + i.toString().padStart(2, '0')); // Заполняем атрибут соответствующей датой
            n++;
        }



        for(var j = 0; j < 42; j++) {
            if(days[j].innerHTML === ""){
                days[j].id = "disabled";
            }
            else if(j === day + startDay - 1){
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
        var selected = document.querySelector(".selected");
        if (selected) {
            selected.classList.remove("selected");
        }
        o.classList.add("selected");

        var dayText = o.querySelector('.day').textContent; // Получаем текст дня из span.day
        var ticketInfo = JSON.parse(o.getAttribute('data-ticket-info')); // Распарсим JSON
        selectedDay = new Date(year, month, dayText);
        this.drawHeader(dayText, ticketInfo); // Передаем текст дня и распарсенный JSON
    };



    Calendar.prototype.preMonth = function() {
        if(month < 1){
            month = 11;
            year = year - 1;
        }else{
            month = month - 1;
        }
        this.drawHeader(1);
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
        this.drawDays();
        onChangeWagonType();
    };

    var calendar = new Calendar();

}, false);

})(jQuery);




function displayResults(data, selectedWagonType) {
    globalData = data;
    var calendarTable = document.getElementById('calendar');
    var cells = calendarTable.querySelectorAll('td');

    for (var i = 0; i < cells.length; i++) {
        var cell = cells[i];
        var priceElement = cell.querySelector('.price');
        if (priceElement) {
            priceElement.textContent = '';
        }
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
    var selectedWagonType = wagonTypeSelector.value;
    if (globalData) {
        displayResults(globalData, selectedWagonType);
    }
}

wagonTypeSelector.addEventListener('change', onChangeWagonType);


function updatePriceClasses() {
  const priceElements = document.querySelectorAll('.price');
  const prices = [];

  priceElements.forEach(element => {
    const price = parseFloat(element.textContent);
    prices.push(price);
  });

  const minPrice = Math.min(...prices);
  const averagePrice = prices.reduce((sum, price) => sum + price, 0) / prices.length;

  priceElements.forEach(element => {
    const price = parseFloat(element.textContent);

    element.classList.remove('cheapper', 'most-cheapper', 'expensive');

    if (price === minPrice) {
      element.classList.add('cheapper');
    } else if (price < averagePrice) {
      element.classList.add('most-cheapper');
    } else if (price > averagePrice) {
      element.classList.add('expensive');
    }
  });
}