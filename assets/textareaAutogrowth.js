window.autoGrowTextarea = function (el) {
  const maxLines = 5;
  const lineHeight = 24; // adjust to match your CSS
  const maxHeight = maxLines * lineHeight;
  const numLines = el.value.split(/\r\n|\r|\n/).length;

  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, maxHeight) + "px";
  el.style.lineHeight = numLines <= 1 ? "36px" : "20px";


  el.style.overflowY =
    el.scrollHeight > maxHeight ? "auto" : "hidden";
};
