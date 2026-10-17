# Microphone dictation for the chat tutor: implementation plan

Status: approved and implemented, October 16, 2026, except the manual check with a real microphone. Decisions: the browser's default speech service; spoken words fill the question box, and the student presses Send.

## Context

The user asked how hard it is to let students speak their questions to the chat tutor. Today a student types into the "Ask the tutor" box (`ui/index.html` lines 76-80) and presses Send or Enter.

Intended outcome: a microphone button beside Send. The student speaks, reads the words in the box, corrects them, and sends.

## How hard it is

Small. The browser does the speech recognition with its built-in Web Speech API. Our code adds one button and one script of about 60 lines. It also adds three CSS rules, about six lines in app.js, a README paragraph, and one browser test. The server and the Python code do not change, and the course needs no new package. Estimate: half a day, with tests and a manual check.

The browser API keeps the work small. It also sets the limits:

| Browser | Microphone button | Who hears the audio |
|---|---|---|
| Chrome (desktop) | Yes | Google |
| Edge | Yes | Microsoft |
| Safari 14.1+ | Yes, as `webkitSpeechRecognition` | Apple. Siri or Dictation must be on in macOS settings. |
| Firefox 157 (release) | No. Only preview builds have the API. | Nobody |
| Brave, some Linux Chromium builds | Shows, then fails with a `network` error | Nobody. These builds have no speech service. |

Facts in the code that keep it small:
- The server binds to 127.0.0.1 (`server.py` line 1379), and start.sh opens http://localhost:8107. Browsers treat localhost as a secure context, so they allow the microphone without HTTPS.
- The server sends no Content-Security-Policy or Permissions-Policy header. Nothing blocks the microphone.
- server.py serves any flat file in ui/ (`server.py` lines 1230-1234). A new ui/dictation.js needs no server change.
- The repo has no speech or audio code now.

## Behavior

- The microphone button sits between the question box and Send. Browsers without speech recognition do not show it.
- A click starts listening, and the button turns red. The browser asks for microphone permission the first time.
- Words appear in the box while the student speaks. They follow any text already in the box, after one space.
- A second click stops listening. The last words still arrive. Then the focus goes to the box, so Enter sends.
- Dictation never sends. The student reads the words, fixes a misheard term such as LAANC, and presses Send.
- Send stops listening at once and drops words still to come. Late words cannot reappear in the emptied box.
- Typing while the microphone is on stops listening. The typed text stays.
- The practice exam pauses the chat. The microphone button is then off, as the box is.
- If dictation fails, the chat shows why in a red message. The existing "Could not reach the course server" message uses the same style.
- Silence at the start shows no message. The button just goes back.
- The language is US English (`en-US`).

## Files to change

| File | Change |
|---|---|
| `ui/dictation.js` (new) | The module: `window.Dictation = { attach, cancel }`. |
| `ui/index.html` | The `#chat-mic` button with an inline SVG icon. A `dictation.js` script tag before app.js. |
| `ui/app.js` | Three small edits: start-up, `submitChat`, `setChatState`. |
| `ui/styles.css` | Icon size, the listening color, and `min-width: 0` on the chat textarea. |
| `README.md` | A "Speaking a question" paragraph after "Run it". |
| `tests/fixtures/dictation.html`, `tests/test_dictation.py` (new) | The browser test. |
| `tests/fixtures/chat_drawing.html`, `tests/fixtures/panels.html` | These load app.js, so they need the script tag. chat_drawing.html also needs the button in its hand-written form. |
| `docs/plans/microphone-dictation.md` (new) | This plan, with "As built" at the end, as for earlier plans. |

No server, prompt, ledger, or packaging change.

## Design

### ui/dictation.js (new)

Same style as `ui/panels.js`: an ES5 IIFE with `"use strict"`, a header comment, and a `window.*` export. The header comment says which company hears the audio in each browser.

```js
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
    if (r !== running) { return; }   // already over, or cancelled
    running = null;
    button.setAttribute("aria-pressed", "false");
    if (document.activeElement === button) { box.focus(); }
  }

  button.hidden = false;
  button.addEventListener("click", function () {
    if (running) { running.stop(); return; }   // the last words arrive, then "end"
    var r = new Recognition(), before = box.value;
    if (before && !/\s$/.test(before)) { before += " "; }
    r.lang = "en-US";
    r.continuous = true;       // a pause does not end it
    r.interimResults = true;   // words show while the student speaks
    r.onresult = function (e) {
      if (r !== running) { return; }   // cancelled: drop the words
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
      if (e.error !== "no-speech") { onError(MESSAGES[e.error] || "Speech recognition stopped: " + (e.message || e.error) + "."); }
      finish(r);
    };
    r.onend = function () { finish(r); };
    running = r;
    button.setAttribute("aria-pressed", "true");
    r.start();
  });

  // Send, the practice exam, or typing: stop now and drop words still to come.
  cancel = function () {
    var r = running;
    if (r) { finish(r); r.abort(); }
  };
  box.addEventListener("input", function () { cancel(); });
}

window.Dictation = { attach: attach, cancel: function () { cancel(); } };
```

Why these parts are there:
- `r !== running` drops events from a cancelled session. Chrome and Safari can deliver a result after `abort()`.
- `trim()` and `join(" ")`: Chrome starts each later result with a space, and Safari does not. Plain joining glues Safari's words together.
- `onerror` ends the session itself. Safari fires `error` and no `end` for permission failures.
- The `input` event fires for typing, not for `box.value = ...`. So dictation does not cancel itself.

### ui/app.js

Reuse `appendChat` and `el` for the error message, as `sendChat` does (`ui/app.js` lines 572-575).

1. `setChatState` (`ui/app.js` lines 521-526): add
   ```js
   document.getElementById("chat-mic").disabled = chat.paused;
   if (chat.paused) { Dictation.cancel(); }
   ```
2. `submitChat` (`ui/app.js` lines 724-728): add `Dictation.cancel();` after the guard, before `sendChat`.
3. Start-up, after the Enter handler (`ui/app.js` lines 733-739):
   ```js
   Dictation.attach(document.getElementById("chat-mic"), input, function (text) {
     appendChat(el("div", { class: "msg tutor error" }, text));
   });
   ```

### ui/index.html

Between the textarea and Send:

```html
<button id="chat-mic" type="button" hidden aria-pressed="false" aria-label="Speak your question"
        title="Speak your question. Your browser's speech service turns it into text."><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/></svg></button>
```

The icon copies the pattern of `CourseTree.laneGlyph()` (`ui/course-tree.js` lines 396-401). It uses `stroke="currentColor"`, so it takes the accent color and the dark theme. Add `<script src="dictation.js"></script>` after instructor.js, before app.js.

### ui/styles.css

```css
.chat-form textarea { /* existing rules, plus: */ min-width: 0; }
#chat-mic svg { width: 1em; height: 1em; vertical-align: -0.125em; }
#chat-mic[aria-pressed="true"] { color: var(--surface); background: var(--bad); border-color: var(--bad); }
```

- `min-width: 0`: a textarea in a flex row does not shrink below its default width of 20 columns. At the narrowest chat panel (300 px), the new button can push Send past the panel edge. Test check 2 decides this. If check 2 passes without the rule, leave the textarea rule unchanged.
- The icon at 1em keeps the button as tall as Send.
- `.chat-form button` sets no `display`, so the `hidden` attribute works.

### README.md

Proposed paragraph, after "Then open http://localhost:8107 ...":

> **Speaking a question.** With the microphone button beside Send, a student can speak a question. The browser's own speech recognition turns it into text. Chrome sends the audio to Google, Edge to Microsoft, and Safari to Apple. Safari needs Siri or Dictation turned on in macOS settings. Firefox has no speech recognition, so it shows no button. Brave shows the button but has no speech service. The words go into the question box. Nothing goes to the tutor until the student presses Send. The speech service needs the internet, also with the offline `ollama` backend.

## Implementation steps

1. Copy this plan to `docs/plans/microphone-dictation.md`, with link paths fixed for that folder.
2. Write `tests/fixtures/dictation.html` and `tests/test_dictation.py`. Verify: the test fails, because there is no button yet.
3. Add dictation.js, the markup, the CSS, and the app.js edits. Verify: `python3 -m unittest discover -s tests -p test_dictation.py -v` passes.
4. Update chat_drawing.html and panels.html. Verify: `python3 -m unittest discover -s tests -v` passes in full.
5. Break each covered behavior on purpose, one at a time. Verify: the matching check fails each time.
6. Add the README paragraph.
7. Do the manual check below.
8. Write "As built" in the docs/plans copy.

## Testing approach

### Automatic test (headless Chrome)

`tests/test_dictation.py` follows `tests/test_layout.py`. It imports `CHROME`, `ROOT`, and `Quiet` from test_markdown.py and serves the repo on a free port. It runs Chrome with `--dump-dom --window-size=1600,1000 --virtual-time-budget=5000` and expects "PASS". It has two tests: the default mode and `?none`.

`tests/fixtures/dictation.html`:
- Loads the real index.html body with a synchronous XHR, as `tests/fixtures/panels.html` does, and links styles.css.
- Stubs `fetch`. `/api/state` and `/api/chat` answer as in chat_drawing.html. `/api/ask` records the payload and never answers.
- Stubs `window.Instructor` and keeps the shared functions, so the fixture can call `refresh()` later.
- Puts a fake recognizer on both `SpeechRecognition` and `webkitSpeechRecognition`, because Chrome has a real one. The fake records `start`, `stop`, and `abort`. The fixture fires its `onresult`, `onerror`, and `onend`.
- In `?none`, sets both names to `undefined`.
- Loads marked.min.js, markdown.js, course-tree.js, dictation.js, and app.js.

Checks in the default mode, in this order:
1. The button shows, and it is as tall as Send.
2. With the chat panel at 300 px (`--right`), the button and Send fit inside the form.
3. A click starts one recognizer with `en-US`, continuous mode, and interim results. The button is pressed.
4. Spoken words follow typed words after one space. Results with a leading space (Chrome) and without one (Safari) both give separate words.
5. A second click calls `stop`, not `abort`. The `end` event releases the button and puts the focus in the box.
6. Dictation alone sends nothing: no `/api/ask` call and no student message.
7. Typing while listening calls `abort`, releases the button, and keeps the typing.
8. A `not-allowed` error shows the permission message in the chat. It releases the button with no `end` event, as Safari does.
9. A `no-speech` error shows no message.
10. Enter while listening calls `abort` and sends the dictated question to `/api/ask`. A late result leaves the box empty. This check comes after the others, because the chat stays busy after it.
11. The practice exam: the fixture starts listening, then calls `refresh()` with `mock_in_progress`. After a timer, it checks that the recognizer got `abort` and the button is off.

In `?none`: the button stays hidden (`offsetWidth` is 0).

### Existing tests

chat_drawing.html (run by test_markdown.py) and panels.html (run by test_layout.py) load app.js. Without the script tag, app.js stops at start-up. Then run `python3 -m unittest discover -s tests -v`. All tests must pass.

### Manual check (Chrome 153 on this machine, real microphone)

1. Run `./start.sh`. Click the microphone and allow it. Say "What is the maximum altitude for a small unmanned aircraft?" The words show while you speak. Click again, check the text, and press Enter. The tutor answers.
2. Say aviation terms: LAANC, Remote ID, METAR, Class B airspace, 400 feet AGL, part 107.51. Write down the misheard terms.
3. Type while listening. Listening stops, and the typing stays.
4. Block the microphone in the site settings, then click the button. The chat shows the permission message.
5. Start the practice exam. The microphone button is off.
6. Open the course in Firefox 157. There is no microphone button.
7. Check the button in the light and dark themes, and with the chat panel at its narrowest.
8. If a Mac is available, try Safari with Dictation on and off.

## Risks

- Safari is not testable on this machine. Users of Safari 15 and 16 reported repeated words in continuous mode. If the Mac test shows repeats, add a step that removes repeats to the join.
- Speech services can mishear aviation terms. The student fixes them before sending. Chrome 142+ takes phrase hints (`phrases`), but its cloud service can refuse them with a `phrases-not-supported` error.
- Privacy: Google, Microsoft, or Apple hears the student's voice. The README and the button tooltip say so. With the `ollama` backend, the tutor is offline, but dictation is not.

## Not in this change

- On-device recognition (Chrome 139+ `processLocally`) and phrase hints for aviation terms.
- A microphone for the instructor's authoring assistant. It uses the same `.chat-form`. The module keeps one `cancel` for one box, so a second box needs a small change.
- Reading answers aloud, and a record of whether a question was spoken.

## Noticed, not in this change

- The README calls `anthropic` the default backend (lines 102 and 118). config.json ships `"provider": "claude_code"`, and tools/package.py does not change it. A zip made now would start the `claude_code` backend.

## Sources

- [MDN: SpeechRecognition](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition)
- [MDN browser compatibility data: SpeechRecognition](https://github.com/mdn/browser-compat-data/blob/main/api/SpeechRecognition.json)
- [MDN: Using the Web Speech API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API/Using_the_Web_Speech_API)
- [MDN: SpeechRecognitionErrorEvent.error](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionErrorEvent/error)
- [WebKit bug 225298: Safari needs Siri or Dictation on](https://bugs.webkit.org/show_bug.cgi?id=225298)
- [Apple developer forum: repeated words in Safari](https://developer.apple.com/forums/thread/694847)
- [Brave issue 2802: no speech service](https://github.com/brave/brave-browser/issues/2802)
- [Microsoft Edge: speech recognition](https://learn.microsoft.com/en-us/microsoft-edge/web-platform/speech-recognition-api)

## As built

The implementation follows the plan, with these changes:

- **No `min-width: 0` on the textarea.** Chrome 153 shrinks the textarea in the flex row. At a 300 px chat panel the box is 144.5 px wide, and Send fits. Send goes past the edge only at a 160 px panel, and panels.js does not allow that width. Check 2 passed without the rule, so the textarea rule is unchanged. Safari is not measured. If Send goes past the edge there, add the rule.
- **The icon rule has a different reason.** Without `#chat-mic svg`, the button is still as tall as Send (44 px). The rule keeps the icon level with Send's label. Without it, the icon sits about 3 px high (screenshots at 3x scale, light and dark theme).
- **Fixture errors keep the failed checks.** A failed check can leave dictation running, so a later step throws. The fixture now lists the failures found before the error, also inside the practice-exam timer. Before this change, three breaks showed only "ERROR ..." or "NOT RUN".
- **Smoke check through the real server.** A mock course in a temporary folder, served by `CourseServer`: `/dictation.js` comes back as `text/javascript`, the button shows in headless Chrome (which has the real API), and the console has no errors.

Tests: `python3 -m unittest discover -s tests` runs 191 tests, all pass (1 skip, pdftotext). Each new check failed when the code it covers was broken on purpose: 17 breaks in dictation.js and app.js, one at a time. The `#chat-mic svg` rule has no automatic check; the screenshots cover it.

Open: the manual check with a real microphone (steps 1 to 8 above) needs a person at the computer.
