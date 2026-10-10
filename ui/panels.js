(function () {
  "use strict";

  // Panels: progress, lesson and chat side by side. The student sets the
  // widths of the two side panels by dragging the dividers beside the lesson,
  // or by focusing a divider and pressing the left and right arrow keys. The
  // widths are the --left and --right variables on main.layout (the defaults
  // are in styles.css). They stay within limits, so no panel gets too narrow,
  // and localStorage keeps them for the next page load.
  var MIN = { left: 300, right: 300 }, MIN_LESSON = 400, STEP = 20, KEY = "part107.panels";

  document.addEventListener("DOMContentLoaded", function () {
    var layout = document.querySelector(".layout"), dividers = {}, want = {}, shown = {};
    Array.prototype.forEach.call(layout.querySelectorAll(".divider"), function (d) {
      var side = d.getAttribute("data-side");
      dividers[side] = d;
      want[side] = parseFloat(getComputedStyle(layout).getPropertyValue("--" + side));
    });
    try {
      var saved = JSON.parse(localStorage.getItem(KEY));
      if (saved && saved.left > 0 && saved.right > 0) { want = { left: saved.left, right: saved.right }; }
    } catch (e) { /* no storage: the default widths */ }

    // The width the two side panels and the lesson share.
    function room() {
      var style = getComputedStyle(layout);
      return layout.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) -
        dividers.left.offsetWidth - dividers.right.offsetWidth;
    }

    // Show the wanted widths as far as the window allows. On a narrow window
    // the chat panel gives way first, then the progress panel, each down to
    // its minimum.
    function show() {
      var space = room();
      shown.left = Math.max(MIN.left, Math.min(want.left, space - MIN_LESSON - MIN.right));
      shown.right = Math.max(MIN.right, Math.min(want.right, space - MIN_LESSON - shown.left));
      ["left", "right"].forEach(function (side) {
        var other = side === "left" ? "right" : "left";
        layout.style.setProperty("--" + side, shown[side] + "px");
        dividers[side].setAttribute("aria-valuenow", Math.round(shown[side]));
        dividers[side].setAttribute("aria-valuemin", MIN[side]);
        dividers[side].setAttribute("aria-valuemax", Math.round(Math.max(MIN[side], space - MIN_LESSON - shown[other])));
      });
    }

    // A new width for one side panel, within its limits.
    function resize(side, width) {
      var other = side === "left" ? "right" : "left";
      want[side] = Math.max(MIN[side], Math.min(width, room() - MIN_LESSON - shown[other]));
      show();
    }

    function save() {
      try { localStorage.setItem(KEY, JSON.stringify(want)); } catch (e) { /* not kept */ }
    }

    Object.keys(dividers).forEach(function (side) {
      // A divider moves the way the pointer or the arrow key goes, so the
      // right one makes the chat panel narrower when it moves right.
      var divider = dividers[side], sign = side === "left" ? 1 : -1;
      divider.addEventListener("pointerdown", function (e) {
        if (e.button !== 0) { return; }
        e.preventDefault();
        var startX = e.clientX, start = shown[side];
        function move(ev) { resize(side, start + sign * (ev.clientX - startX)); }
        function stop() {
          document.removeEventListener("pointermove", move);
          document.removeEventListener("pointerup", stop);
          document.removeEventListener("pointercancel", stop);
          divider.classList.remove("dragging");
          document.body.classList.remove("resizing");
          save();
        }
        divider.classList.add("dragging");
        document.body.classList.add("resizing");
        document.addEventListener("pointermove", move);
        document.addEventListener("pointerup", stop);
        document.addEventListener("pointercancel", stop);
      });
      divider.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") { return; }
        e.preventDefault();
        resize(side, shown[side] + sign * (e.key === "ArrowRight" ? STEP : -STEP));
        save();
      });
    });
    window.addEventListener("resize", show);
    show();
  });
})();
