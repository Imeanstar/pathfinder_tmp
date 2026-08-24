// majorpath(Next.js)의 Reveal.tsx / FadeOutOnScroll.tsx 동작을 그대로 이식.
// - .reveal: 뷰포트에 들어오면 살짝 올라오며 페이드인 (IntersectionObserver, 한 번만)
// - .fade-hero: 스크롤한 만큼 위로 사라지며 살짝 축소 (rAF로 스로틀)

document.addEventListener("DOMContentLoaded", () => {
  const revealEls = document.querySelectorAll(".reveal");
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: "0px 0px -60px 0px" }
  );
  revealEls.forEach((el) => {
    const delay = el.dataset.delay;
    if (delay) el.style.transitionDelay = `${delay}ms`;
    observer.observe(el);
  });

  const hero = document.getElementById("heroSection");
  if (hero) {
    let ticking = false;
    const update = () => {
      ticking = false;
      const rect = hero.getBoundingClientRect();
      const height = rect.height || 1;
      const raw = -rect.top / height;
      const progress = Math.min(Math.max(raw, 0), 1);
      const translateY = progress * -60;
      const scale = 1 - progress * 0.05;
      hero.style.transform = `translateY(${translateY}px) scale(${scale})`;
      hero.style.opacity = String(1 - progress);
    };
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
  }

  // #startBtn 클릭 처리는 auth.js가 전담한다(로그인 여부에 따라 분기) — 여기서
  // 같이 리스너를 걸면 auth.js의 로그인 게이트를 우회하게 된다(PR #1 머지 시
  // 발견한 충돌, 2026-08-24).
});
