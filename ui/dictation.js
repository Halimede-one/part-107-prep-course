(function () {
  "use strict";

  // Dictation: the student speaks a question instead of typing it. The
  // browser's own speech recognition (the Web Speech API) turns the speech into
  // words, which appear in the question box while the student speaks. The
  // student reads them, corrects a misheard term, and sends; speaking never
  // sends. The browser decides who hears the audio: Chrome sends it to Google,
  // Edge to Microsoft, Safari to Apple. Firefox has no speech recognition, so
  // the microphone button stays hidden there.
  var MESSAGES = {
    "not-allowed": "The course did not get permission to use the microphone. Allow it in the browser's site settings, then try again.",
    "service-not-allowed": "This browser does not allow speech recognition. On a Mac, turn on Siri or Dictation in System Settings.",
    "audio-capture": "No microphone was found.",
    "network": "The browser could not reach its speech service. Some browsers, such as Brave, have none. Use Chrome, Edge or Safari, or type the question."
  };
  var cancel = function () {};

  // button: the microphone button. box: the question box. onError(text): shows why dictation failed.
  function attach(button, box, onError) {
    var Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { return; }
    var running = null;

    // The session is over: release the button; the box takes the keys again.
    function finish(r) {
      if (r !== running) { return; }  // already over, or cancelled
      running = null;
      button.setAttribute("aria-pressed", "false");
      if (document.activeElement === button) { box.focus(); }
    }

    button.hidden = false;
    button.addEventListener("click", function () {
      if (running) { running.stop(); return; }  // the last words arrive, then "end"
      var r = new Recognition(), before = box.value;
      if (before && !/\s$/.test(before)) { before += " "; }
      r.lang = "en-US";
      r.continuous = true;      // a pause does not end it
      r.interimResults = true;  // words show while the student speaks
      r.onresult = function (e) {
        if (r !== running) { return; }  // cancelled: drop the words
        // Chrome starts each later result with a space and Safari does not, so
        // trim each one and join them with one space.
        var words = [];
        for (var i = 0; i < e.results.length; i++) {
          var t = e.results[i][0].transcript.trim();
          if (t) { words.push(t); }
        }
        box.value = before + words.join(" ");
      };
      // Safari ends some sessions with "error" and no "end".
      r.onerror = function (e) {
        if (r !== running) { return; }
        if (e.error !== "no-speech") {
          onError(MESSAGES[e.error] || "Speech recognition stopped: " + (e.message || e.error) + ".");
        }
        finish(r);
      };
      r.onend = function () { finish(r); };
      running = r;
      button.setAttribute("aria-pressed", "true");
      r.start();
    });

    // Send, the practice exam, or typing: stop now and drop words still to
    // come. Chrome and Safari can still deliver a result after abort().
    cancel = function () {
      var r = running;
      if (r) { finish(r); r.abort(); }
    };
    // "input" fires for typing, not for box.value = ..., so the words that
    // dictation writes do not cancel it.
    box.addEventListener("input", function () { cancel(); });
  }

  window.Dictation = { attach: attach, cancel: function () { cancel(); } };
})();
