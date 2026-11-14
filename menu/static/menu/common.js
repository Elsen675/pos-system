// Ümumi köməkçilər. Qayda: istifadəçi mətnini HƏMİŞƏ textContent ilə yaz,
// innerHTML ilə yox. innerHTML mətni HTML kimi icra edir, məsələn qeyd sahəsinə
// "<img src=x onerror=...>" yazan müştəri işçinin brauzerində kod işlədə bilərdi (XSS).

function getCookie(name) {
  const parts = document.cookie ? document.cookie.split('; ') : [];
  for (const part of parts) {
    const idx = part.indexOf('=');
    if (part.slice(0, idx) === name) return decodeURIComponent(part.slice(idx + 1));
  }
  return null;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
