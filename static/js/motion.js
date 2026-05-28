(() => {
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const markReady = () => document.body.classList.add("page-ready");
  if (reduceMotion) {
    markReady();
    return;
  }

  requestAnimationFrame(markReady);

  const header = document.querySelector(".site-header");
  if (header) {
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        header.classList.toggle("header-scrolled", window.scrollY > 6);
        ticking = false;
      });
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  const revealTargets = document.querySelectorAll(
    ".motion-reveal"
  );
  if (!revealTargets.length) return;

  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      });
    },
    { rootMargin: "0px 0px -6% 0px", threshold: 0.12 }
  );

  revealTargets.forEach((el) => observer.observe(el));
})();
