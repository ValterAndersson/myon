// ==========================================================================
// Povver Landing — Scroll animations, smooth scroll, mobile nav, analytics
// ==========================================================================

(function () {
  "use strict";

  var prefersReducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  // --- Analytics helper (no-op until GA4 loads) ---

  function track(event, params) {
    if (window.gtag) {
      window.gtag("event", event, params);
    }
  }

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

  // --- Section view tracking ---

  var sectionNames = {
    0: "proactive_intelligence",
    1: "conversational_coaching",
    2: "set_logging_grid",
    3: "train_your_way"
  };

  var sectionObserver = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var index = Array.prototype.indexOf.call(
            document.querySelectorAll(".feature-section"),
            entry.target
          );
          var name = sectionNames[index] || "feature_" + index;
          track("section_view", { section_name: name, section_index: index + 1 });
          sectionObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.3 }
  );

  document.querySelectorAll(".feature-section").forEach(function (el) {
    sectionObserver.observe(el);
  });

  // CTA and highlights sections
  var ctaSection = document.getElementById("download");
  if (ctaSection) {
    var ctaObserver = new IntersectionObserver(
      function (entries) {
        if (entries[0].isIntersecting) {
          track("section_view", { section_name: "cta_download" });
          ctaObserver.unobserve(entries[0].target);
        }
      },
      { threshold: 0.3 }
    );
    ctaObserver.observe(ctaSection);
  }

  // --- App Store button click tracking ---

  document.querySelectorAll(".store-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      // Determine location: hero or final CTA
      var inHero = !!btn.closest(".hero");
      var location = inHero ? "hero" : "cta_footer";

      track("app_store_click", {
        link_location: location,
        link_url: btn.getAttribute("href") || ""
      });
    });
  });

  // --- Nav CTA click tracking ---

  var navCta = document.querySelector(".nav-cta");
  if (navCta) {
    navCta.addEventListener("click", function () {
      track("app_store_click", {
        link_location: "nav",
        link_url: navCta.getAttribute("href") || ""
      });
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

  // --- Cookie Consent Banner ---

  var cookieBanner = document.getElementById("cookie-banner");
  var cookieAccept = document.getElementById("cookie-accept");
  var cookieDecline = document.getElementById("cookie-decline");

  if (cookieBanner && cookieAccept && cookieDecline) {
    var consent = localStorage.getItem("povver_cookie_consent");

    if (consent === null) {
      // No choice made yet — show banner after a short delay
      setTimeout(function () {
        cookieBanner.classList.add("visible");
      }, 1500);
    } else if (consent === "accepted") {
      loadAnalytics();
    }

    cookieAccept.addEventListener("click", function () {
      localStorage.setItem("povver_cookie_consent", "accepted");
      cookieBanner.classList.remove("visible");
      loadAnalytics();
      // cookie_consent_accepted fires after GA4 init (loadAnalytics is async)
      setTimeout(function () {
        track("cookie_consent_accepted");
      }, 1000);
    });

    cookieDecline.addEventListener("click", function () {
      localStorage.setItem("povver_cookie_consent", "declined");
      cookieBanner.classList.remove("visible");
      var declineCount = parseInt(localStorage.getItem("povver_cookie_decline_count") || "0", 10);
      localStorage.setItem("povver_cookie_decline_count", String(declineCount + 1));
    });
  }

  function loadAnalytics() {
    if (window._gaLoaded) return;
    window._gaLoaded = true;

    var gaId = "G-V9YHQNJTB7";
    var script = document.createElement("script");
    script.async = true;
    script.src = "https://www.googletagmanager.com/gtag/js?id=" + gaId;
    document.head.appendChild(script);

    script.onload = function () {
      window.dataLayer = window.dataLayer || [];
      function gtag() { window.dataLayer.push(arguments); }
      window.gtag = gtag;
      gtag("js", new Date());
      gtag("config", gaId, { anonymize_ip: true });

      // Fire landing_page_viewed after GA4 initializes
      var params = { referrer: document.referrer || "(direct)" };
      var urlParams = new URLSearchParams(window.location.search);
      if (urlParams.get("utm_source")) params.utm_source = urlParams.get("utm_source");
      if (urlParams.get("utm_medium")) params.utm_medium = urlParams.get("utm_medium");
      if (urlParams.get("utm_campaign")) params.utm_campaign = urlParams.get("utm_campaign");
      gtag("event", "landing_page_viewed", params);
    };
  }
})();
