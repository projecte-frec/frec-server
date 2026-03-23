window.autoGrowTextarea = function (el) {
  const maxLines = 5;
  const lineHeight = 24; // adjust to match your CSS
  const maxHeight = maxLines * lineHeight;

  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, maxHeight) + "px";

  el.style.overflowY =
    el.scrollHeight > maxHeight ? "auto" : "hidden";
};
