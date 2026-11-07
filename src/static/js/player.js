// Play buttons for Deezer previews: one song at a time, the button toggles play and pause.
(function () {
  var audio = new Audio();
  var current = null;
  document.addEventListener("click", function (e) {
    var btn = e.target.closest(".mm-play");
    if (!btn) return;
    if (current === btn && !audio.paused) {
      audio.pause();
      btn.innerHTML = "&#9654;";
      return;
    }
    if (current) current.innerHTML = "&#9654;";
    audio.src = btn.dataset.src;
    audio.play();
    current = btn;
    btn.innerHTML = "&#10074;&#10074;";
  });
  audio.addEventListener("ended", function () {
    if (current) current.innerHTML = "&#9654;";
  });
  // Only one of the full players on the ranking pages plays at a time
  document.addEventListener("play", function (e) {
    if (e.target.classList && e.target.classList.contains("mm-audio")) {
      audio.pause();
      document.querySelectorAll("audio.mm-audio").forEach(function (a) { if (a !== e.target) a.pause(); });
    }
  }, true);
})();
