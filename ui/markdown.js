(function () {
  "use strict";

  // Tutor text is Markdown, rendered with marked (marked.min.js, v15.0.12).
  // The text comes from a model, so it must never run code in the page: raw
  // HTML in it shows as text, and links and images keep only http, https and
  // relative URLs. A relative image such as images/x.png is served from the
  // curriculum's images folder.
  var parser = new marked.Marked({
    renderer: {
      html: function (token) { return escape(token.text); },
      // A fenced block that starts ```svg is a drawing by the tutor, shown as
      // an image, where code in an SVG cannot run. The rest of the first line
      // describes it. Until the SVG is complete, as while it streams, a note
      // stands in for it. Other code blocks render as code.
      code: function (token) {
        if (!/^svg(\s|$)/.test(token.lang || "")) { return false; }
        if (!/<\/svg>\s*$/i.test(token.text)) { return '<p class="drawing">Drawing a picture…</p>'; }
        var svg = token.text.replace(/<svg(?![^>]*xmlns=)/i, '<svg xmlns="http://www.w3.org/2000/svg"');
        return '<img class="drawn" alt="' + escape(token.lang.slice(3).trim() || "Drawing") +
          '" src="data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg) + '">';
      }
    }
  });

  function escape(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function safeUrl(value) {
    try {
      return /^https?:$/.test(new URL(value, document.baseURI).protocol);
    } catch (e) {
      return false;
    }
  }

  // The rendered HTML as nodes. Links open in a new tab, like the citations.
  // Only the code renderer above makes an img.drawn: raw HTML never becomes
  // an element, so the text cannot make one.
  function toNodes(html) {
    var template = document.createElement("template");
    template.innerHTML = html;
    Array.prototype.forEach.call(template.content.querySelectorAll("a, img:not(.drawn)"), function (node) {
      var link = node.tagName === "A";
      if (!safeUrl(node.getAttribute(link ? "href" : "src"))) {
        node.replaceWith(link ? node.textContent : node.alt);
      } else if (link) {
        node.target = "_blank";
        node.rel = "noopener";
      }
    });
    return template.content;
  }

  window.markdown = {
    // Paragraphs, lists, tables, images, drawings: for bodies, feedback and answers.
    block: function (text) { return toNodes(parser.parse(text || "")); },
    // Bold, italic, code and links only: for titles, stems and options.
    inline: function (text) { return toNodes(parser.parseInline(text || "")); }
  };
}());
