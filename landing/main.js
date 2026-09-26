(() => {
  const root = document.documentElement;
  const themeToggle = document.getElementById("theme-toggle");
  const menuToggle = document.getElementById("menu-toggle");
  const navigation = document.getElementById("site-nav");
  const themeColor = document.querySelector('meta[name="theme-color"]');
  const themeStorageKey = "vf-marketing-theme";
  const icons = { light: "#i-sun", dark: "#i-moon" };
  const consoleBaseUrl = (window.VF_CONFIG?.CONSOLE_BASE_URL || "http://localhost:3000").replace(/\/$/, "");

  document.querySelectorAll(".console-link").forEach((link) => {
    link.href = `${consoleBaseUrl}/login`;
  });

  function setTheme(theme, persist = false) {
    const resolvedTheme = theme === "light" ? "light" : "dark";
    root.dataset.theme = resolvedTheme;
    themeToggle.setAttribute("aria-label", `Switch to ${resolvedTheme === "dark" ? "light" : "dark"} theme`);
    themeToggle.title = `Switch to ${resolvedTheme === "dark" ? "light" : "dark"} theme`;
    themeToggle.innerHTML = `<svg class="icon" aria-hidden="true"><use href="${icons[resolvedTheme]}" /></svg>`;
    themeColor.content = resolvedTheme === "dark" ? "#030711" : "#f8fafd";

    if (persist) {
      try {
        window.localStorage.setItem(themeStorageKey, resolvedTheme);
      } catch {
        // The selected theme remains active for this page view when storage is unavailable.
      }
    }
  }

  let savedTheme = null;
  try {
    savedTheme = window.localStorage.getItem(themeStorageKey);
  } catch {
    // Use the default theme when storage is unavailable.
  }
  setTheme(savedTheme === "light" ? "light" : "dark");

  themeToggle.addEventListener("click", () => {
    setTheme(root.dataset.theme === "dark" ? "light" : "dark", true);
  });

  function closeNavigation() {
    navigation.classList.remove("is-open");
    menuToggle.setAttribute("aria-expanded", "false");
    menuToggle.setAttribute("aria-label", "Open navigation");
    menuToggle.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-menu" /></svg>';
  }

  menuToggle.addEventListener("click", () => {
    const isOpen = navigation.classList.toggle("is-open");
    menuToggle.setAttribute("aria-expanded", String(isOpen));
    menuToggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
    menuToggle.innerHTML = `<svg class="icon" aria-hidden="true"><use href="#${isOpen ? "i-close" : "i-menu"}" /></svg>`;
  });

  navigation.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeNavigation);
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeNavigation();
  });

  document.getElementById("year").textContent = String(new Date().getFullYear());

  const revealItems = document.querySelectorAll("[data-reveal]");
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduceMotion || !("IntersectionObserver" in window)) {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  } else {
    root.dataset.revealReady = "true";
    const revealObserver = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -28px" });
    revealItems.forEach((item) => revealObserver.observe(item));
  }
})();
