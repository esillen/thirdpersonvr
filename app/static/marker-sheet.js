const printButton = document.getElementById("printButton");

printButton?.addEventListener("click", () => {
  window.print();
});

setTimeout(() => {
  window.print();
}, 250);
