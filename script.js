/**
 * Portfolio Site JavaScript
 * Handles navigation, smooth scrolling, scroll animations, and form submission
 */

// ===================================
// Navigation & Mobile Menu
// ===================================

const nav = document.getElementById('nav');
const navMenu = document.getElementById('navMenu');
const navToggle = document.getElementById('navToggle');
const navLinks = document.querySelectorAll('.nav__link');

function setMobileMenuOpen(isOpen) {
    if (!navMenu || !navToggle) {
        return;
    }

    navMenu.classList.toggle('active', isOpen);
    navToggle.classList.toggle('active', isOpen);
    navToggle.setAttribute('aria-expanded', String(isOpen));

    if (isOpen) {
        navMenu.querySelector('.nav__link[href]')?.focus();
    } else if (navMenu.contains(document.activeElement)) {
        navToggle.focus();
    }
}

// Toggle mobile menu.
if (navMenu && navToggle) {
    setMobileMenuOpen(false);

    navToggle.addEventListener('click', () => {
        setMobileMenuOpen(!navMenu.classList.contains('active'));
    });
}

// Close mobile menu when a link is clicked.
navLinks.forEach(link => {
    link.addEventListener('click', () => {
        setMobileMenuOpen(false);
    });
});

// Let keyboard users dismiss the menu and return to its trigger.
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && navMenu?.classList.contains('active')) {
        setMobileMenuOpen(false);
        navToggle?.focus();
    }
});

// Mark the canonical nav link for the current page, independent of scroll.
const currentPath = window.location.pathname.replace(/\/+$/, '') || '/';

navLinks.forEach(link => {
    let isCurrent = false;

    try {
        const linkPath = new URL(link.href, window.location.href).pathname.replace(/\/+$/, '') || '/';
        isCurrent = (
            (currentPath.startsWith('/docs/') && linkPath === '/docs/blog.html') ||
            (currentPath === '/projects.html' && linkPath === '/projects.html') ||
            (currentPath === '/reach-out.html' && linkPath === '/reach-out.html')
        );
    } catch {
        isCurrent = false;
    }

    link.classList.toggle('active', isCurrent);
    if (isCurrent) {
        link.setAttribute('aria-current', 'page');
    } else {
        link.removeAttribute('aria-current');
    }
});

// ===================================
// Smooth Scrolling
// ===================================

/**
 * Add smooth scroll behavior to all anchor links
 * This provides a better UX than instant jumps
 */
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const targetId = this.getAttribute('href');
        if (!targetId) {
            return;
        }
        
        // Handle edge case for links to top
        if (targetId === '#' || targetId === '#hero') {
            e.preventDefault();
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
            return;
        }

        const elementId = targetId.startsWith('#') ? targetId.slice(1) : targetId;
        const targetElement = document.getElementById(elementId);
        if (targetElement) {
            e.preventDefault();
            const navHeight = nav ? nav.offsetHeight : 0;
            const targetPosition = targetElement.offsetTop - navHeight;
            
            window.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });
        }
    });
});

// ===================================
// 31 Days of AI: CST 6am Auto-Reveal
// ===================================

function get31DaysAutoDay() {
    // Fixed CST is UTC-6 year-round.
    // Campaign start: Dec 1, 2025 @ 6:00am CST = Dec 1, 2025 @ 12:00 UTC.
    const startUtcMs = Date.UTC(2025, 11, 1, 12, 0, 0);
    const msPerDay = 24 * 60 * 60 * 1000;
    const nowUtcMs = Date.now();

    const rawDay = Math.floor((nowUtcMs - startUtcMs) / msPerDay) + 1;
    const autoDay = Math.min(Math.max(rawDay, 1), 31); // Auto-reveal all 31 days

    return { rawDay, autoDay };
}

function pad2(n) {
    return String(n).padStart(2, '0');
}

function apply31DaysUpdates() {
    const { autoDay } = get31DaysAutoDay();
    const dayText = `Day ${autoDay} of 31`;
    const post = `31-days-ai-day-${pad2(autoDay)}.md`;

    // Homepage banner updates (index.html)
    const bannerCounter = document.getElementById('campaignBannerCounter');
    if (bannerCounter) {
        bannerCounter.textContent = dayText;
    }

    const bannerLatestLink = document.getElementById('campaignBannerLatestLink');
    if (bannerLatestLink) {
        bannerLatestLink.href = `docs/article.html?post=${post}`;
        bannerLatestLink.textContent = `Day ${autoDay}`;
    }

    const bannerReadLink = document.getElementById('campaignBannerReadLink');
    if (bannerReadLink) {
        bannerReadLink.href = `docs/article.html?post=${post}`;
    }

    // Campaign page updates (docs/31-days-of-ai.html)
    const daysPageCounter = document.getElementById('daysPageCounter');
    if (daysPageCounter) {
        daysPageCounter.textContent = dayText;
    }

    const dayCards = document.querySelectorAll('.day-card[data-day]');
    dayCards.forEach(card => {
        const day = parseInt(card.getAttribute('data-day') || '', 10);
        if (!Number.isFinite(day)) {
            return;
        }

        // Keep Day 31 manual/locked; auto-reveal only Days 1-30.
        const shouldUnlock = day <= autoDay && day <= 30;
        if (!shouldUnlock) {
            return;
        }

        card.classList.remove('day-card--locked');

        const badge = card.querySelector('.day-card__badge');
        if (badge) {
            badge.textContent = 'Live';
            badge.classList.remove('day-card__badge--coming');
            badge.classList.add('day-card__badge--live');
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply31DaysUpdates);
} else {
    apply31DaysUpdates();
}

// ===================================
// Scroll Animations (Reveal on Scroll)
// ===================================

/**
 * Animate elements as they scroll into view
 * Adds 'revealed' class which triggers CSS transitions
 * Project cards use staggered delays via data-delay attribute
 */
const revealElements = document.querySelectorAll('.reveal-on-scroll');

const revealOptions = {
    root: null,
    rootMargin: '0px',
    threshold: 0.15 // Trigger when 15% of element is visible
};

const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            // Check if element has a delay attribute (for staggered animations)
            const delay = entry.target.getAttribute('data-delay');
            
            if (delay) {
                // Apply staggered delay for project cards
                setTimeout(() => {
                    entry.target.classList.add('revealed');
                }, parseInt(delay));
            } else {
                // Immediate reveal for non-staggered elements
                entry.target.classList.add('revealed');
            }
            
            // Stop observing after revealing (one-time animation)
            revealObserver.unobserve(entry.target);
        }
    });
}, revealOptions);

// Observe all reveal elements
revealElements.forEach(element => {
    revealObserver.observe(element);
});

// ===================================
// Clickable Cards (Project Cards, Banners, etc.)
// ===================================

/**
 * Make any element with data-href fully clickable
 * Works for project cards, campaign banners, and any other cards
 */
const clickableElements = document.querySelectorAll('[data-href]');

clickableElements.forEach(element => {
    // Add pointer cursor to indicate clickability
    element.style.cursor = 'pointer';
    element.setAttribute('tabindex', '0');
    element.setAttribute('role', 'link');
    
    element.addEventListener('click', (e) => {
        // Don't navigate if clicking on an existing link inside the element
        if (e.target.closest('a')) {
            return;
        }
        
        const href = element.getAttribute('data-href');
        if (href) {
            window.location.href = href;
        }
    });

    element.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const href = element.getAttribute('data-href');
            if (href) {
                window.location.href = href;
            }
        }
    });
});

// ===================================
// Contact Form Handling
// ===================================

const CONTACT_EMAIL = 'josiah.hunter.it@gmail.com';
const contactForm = document.getElementById('contactForm');
const contactSubmit = contactForm?.querySelector('button[type="submit"], input[type="submit"]');
const contactStatus = document.getElementById('contactFormStatus');
const contactStatusMessage = document.getElementById('contactStatusMessage');
const contactDraftLink = document.getElementById('contactDraftLink');
const copyEmailButton = document.getElementById('copyEmailButton');
let latestContactDraftHref = '';

function sanitizeContactSubjectName(value) {
    return String(value).replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function buildContactDraftHref(form) {
    const formData = new FormData(form);
    const name = String(formData.get('name') || '').trim();
    const email = String(formData.get('email') || '').trim();
    const message = String(formData.get('message') || '');
    const subjectName = sanitizeContactSubjectName(name) || 'a website visitor';
    const subject = `Website message from ${subjectName}`;
    const body = `Name: ${name}\nEmail: ${email}\n\n${message}`;

    return `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

function setContactStatus(message, state = '') {
    if (!contactStatus || !contactStatusMessage) {
        return;
    }

    if (state) {
        contactStatus.dataset.state = state;
    } else {
        delete contactStatus.dataset.state;
    }
    contactStatusMessage.textContent = message;

    if (contactDraftLink) {
        contactDraftLink.hidden = !latestContactDraftHref;
        contactDraftLink.href = latestContactDraftHref || `mailto:${CONTACT_EMAIL}`;
    }
}

if (contactForm) {
    if (contactSubmit) {
        contactSubmit.disabled = false;
    }

    contactForm.addEventListener('submit', (event) => {
        event.preventDefault();

        if (!contactForm.reportValidity()) {
            return;
        }

        latestContactDraftHref = buildContactDraftHref(contactForm);
        setContactStatus(
            'Your email app should open with a draft. Review it and press Send there. If nothing opened, use the draft link.',
            'draft'
        );

        if (contactDraftLink) {
            contactDraftLink.click();
        }
    });
}

if (copyEmailButton) {
    copyEmailButton.disabled = false;
    copyEmailButton.addEventListener('click', async () => {
        try {
            if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {
                throw new Error('Clipboard API unavailable');
            }
            await navigator.clipboard.writeText(CONTACT_EMAIL);
            setContactStatus('Email address copied.', 'copy-success');
        } catch {
            setContactStatus(
                `Copying did not work. Select ${CONTACT_EMAIL} or open it in your email app.`,
                'error'
            );
        }
    });
}

// ===================================
// Article Category Filtering
// ===================================

/**
 * Filter articles by category
 * Shows/hides articles based on selected category
 */
const categoryFilters = document.querySelectorAll('.category-filter');
const articleCards = document.querySelectorAll('.article-card:not(.article-card--featured)');

categoryFilters.forEach(filter => {
    filter.addEventListener('click', () => {
        const selectedCategory = filter.getAttribute('data-category');
        
        // Update active filter button
        categoryFilters.forEach(btn => btn.classList.remove('category-filter--active'));
        filter.classList.add('category-filter--active');
        
        // Filter articles
        articleCards.forEach(card => {
            const cardCategories = card.getAttribute('data-categories') || '';
            
            if (selectedCategory === 'all' || cardCategories.includes(selectedCategory)) {
                card.style.display = '';
                // Re-trigger reveal animation if already revealed
                if (card.classList.contains('revealed')) {
                    card.style.animation = 'none';
                    setTimeout(() => {
                        card.style.animation = '';
                    }, 10);
                }
            } else {
                card.style.display = 'none';
            }
        });
        
        // Reset load more button state
        const loadMoreBtn = document.getElementById('loadMoreBtn');
        const hiddenArticles = document.querySelectorAll('.article-card--hidden');
        
        if (loadMoreBtn) {
            // Check if there are any hidden articles in the filtered view
            let hasHiddenVisible = false;
            hiddenArticles.forEach(card => {
                const cardCategories = card.getAttribute('data-categories') || '';
                if (selectedCategory === 'all' || cardCategories.includes(selectedCategory)) {
                    hasHiddenVisible = true;
                }
            });
            
            if (hasHiddenVisible) {
                loadMoreBtn.classList.remove('load-more-btn--hidden');
            } else {
                loadMoreBtn.classList.add('load-more-btn--hidden');
            }
        }
    });
});

// ===================================
// Load More Articles
// ===================================

/**
 * Show hidden articles when "Load More" is clicked
 */
const loadMoreBtn = document.getElementById('loadMoreBtn');

if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
        const hiddenArticles = document.querySelectorAll('.article-card--hidden');
        const activeFilter = document.querySelector('.category-filter--active');
        const selectedCategory = activeFilter ? activeFilter.getAttribute('data-category') : 'all';
        
        let shownCount = 0;
        
        hiddenArticles.forEach(card => {
            const cardCategories = card.getAttribute('data-categories') || '';
            
            // Only show if it matches the current filter
            if (selectedCategory === 'all' || cardCategories.includes(selectedCategory)) {
                card.classList.remove('article-card--hidden');
                shownCount++;
            }
        });
        
        // Hide button if no more hidden articles
        const remainingHidden = document.querySelectorAll('.article-card--hidden');
        let hasMoreToShow = false;
        
        remainingHidden.forEach(card => {
            const cardCategories = card.getAttribute('data-categories') || '';
            if (selectedCategory === 'all' || cardCategories.includes(selectedCategory)) {
                hasMoreToShow = true;
            }
        });
        
        if (!hasMoreToShow) {
            loadMoreBtn.classList.add('load-more-btn--hidden');
        }
    });
}

// ===================================
// Utility: Detect Reduced Motion Preference
// ===================================

/**
 * Respect user's motion preferences for accessibility
 * If user prefers reduced motion, disable animations
 */
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

if (prefersReducedMotion.matches) {
    // Remove animation classes
    document.querySelectorAll('.fade-in, .reveal-on-scroll').forEach(element => {
        element.style.animation = 'none';
        element.style.transition = 'none';
        element.classList.add('revealed');
    });
}

// ===================================
// Page Load Animation
// ===================================

/**
 * Ensure hero animations play on page load
 * This handles cases where JS loads after CSS
 */
window.addEventListener('load', () => {
    document.body.classList.add('loaded');
});

// ===================================
// Console Easter Egg (Optional)
// ===================================

/**
 * A little message for curious developers who check the console
 */
console.log(
    '%cWelcome, fellow developer! 👋',
    'color: #64ffda; font-size: 16px; font-weight: bold;'
);
console.log(
    '%cThis site was built with vanilla HTML, CSS, and JavaScript.',
    'color: #8892b0; font-size: 12px;'
);
console.log(
    '%cFeel free to explore the code on GitHub!',
    'color: #8892b0; font-size: 12px;'
);
