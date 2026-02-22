// ==========================================================================
// Povver Landing — Scroll animations, smooth scroll, mobile nav
// ==========================================================================

(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  // --- Nav scroll state (transparent → frosted) + scroll cue fade ---

  var nav = document.getElementById("nav");
  var hero = document.querySelector(".hero");
  var scrollCue = document.getElementById("scroll-cue");

  if (nav && hero) {
    var updateNav = function () {
      var heroBottom = hero.getBoundingClientRect().bottom;
      if (heroBottom <= nav.offsetHeight) {
        nav.classList.add("nav--scrolled");
      } else {
        nav.classList.remove("nav--scrolled");
      }

      // Fade out scroll cue after scrolling 80px
      if (scrollCue) {
        if (window.scrollY > 80) {
          scrollCue.classList.add("hidden");
        } else {
          scrollCue.classList.remove("hidden");
        }
      }
    };

    window.addEventListener("scroll", updateNav, { passive: true });
    updateNav();
  }

  // --- Fade-in on scroll (IntersectionObserver) ---

  if (!prefersReducedMotion) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );

    document.querySelectorAll(".fade-in").forEach(function (el) {
      observer.observe(el);
    });
  } else {
    document.querySelectorAll(".fade-in").forEach(function (el) {
      el.classList.add("visible");
    });
  }

  // --- Mobile nav toggle ---

  var toggle = document.getElementById("nav-toggle");
  var navLinks = document.getElementById("nav-links");

  if (toggle && navLinks) {
    toggle.addEventListener("click", function () {
      toggle.classList.toggle("active");
      navLinks.classList.toggle("open");
    });

    navLinks.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        toggle.classList.remove("active");
        navLinks.classList.remove("open");
      });
    });
  }

  // --- Smooth scroll for anchor links ---

  document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
    anchor.addEventListener("click", function (e) {
      var targetId = this.getAttribute("href");
      if (targetId === "#") return;

      var target = document.querySelector(targetId);
      if (target) {
        e.preventDefault();
        var navHeight = document.getElementById("nav").offsetHeight;
        var targetPosition =
          target.getBoundingClientRect().top + window.pageYOffset - navHeight;

        window.scrollTo({
          top: targetPosition,
          behavior: prefersReducedMotion ? "auto" : "smooth",
        });
      }
    });
  });
})();
