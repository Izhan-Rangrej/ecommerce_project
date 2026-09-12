/* ============================================================================
   ShopSphere — main.js
   ----------------------------------------------------------------------------
   Progressive enhancement only: every feature on the site ALSO works with
   plain form posts (no JavaScript). This file upgrades the experience:
     * toasts for Django messages + fetch responses
     * add-to-cart via fetch (no page reload) + badge pop animation
     * wishlist toggle via fetch
     * newsletter signup via fetch
     * quantity stepper clamping
     * navbar shadow on scroll
     * reveal-on-scroll (respects prefers-reduced-motion)
   ========================================================================== */
'use strict';

/* ---------------------------------------------------------------------------
 * Helpers
 * --------------------------------------------------------------------------- */

/** Read the CSRF token Django stores in the csrftoken cookie. */
function getCsrfToken() {
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match ? match[1] : '';
}

/** POST form data (or plain object) to url with fetch; returns parsed JSON. */
async function postForm(url, data) {
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'X-CSRFToken': getCsrfToken(),
      'X-Fetch': '1',           // tells our Django views "respond with JSON"
      'Accept': 'application/json',
    },
    body: data instanceof FormData ? data : new URLSearchParams(data),
  });
  let payload = null;
  try { payload = await response.json(); } catch (e) { /* ignore */ }
  return { ok: response.ok, status: response.status, data: payload };
}

/** Show a Bootstrap toast (success | error | warning | info). */
function ssToast(message, type) {
  type = type || 'info';
  const container = document.getElementById('toast-container');
  if (!container || !message) return;

  const icons = {
    success: 'bi-check-circle-fill',
    error: 'bi-x-circle-fill',
    warning: 'bi-exclamation-triangle-fill',
    info: 'bi-info-circle-fill',
  };

  const el = document.createElement('div');
  el.className = `toast ss-toast ss-toast--${type} show`;
  el.setAttribute('role', 'alert');
  el.innerHTML = `
    <div class="d-flex align-items-center">
      <div class="toast-body">
        <i class="bi ss-toast__icon me-2 ${icons[type] || icons.info}"></i>
        <span></span>
      </div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto"
              data-bs-dismiss="toast" aria-label="Close"></button>
    </div>`;
  el.querySelector('span').textContent = message;  // textContent = XSS-safe
  container.appendChild(el);

  const toast = new bootstrap.Toast(el, { delay: 4200 });
  toast.show();
  el.addEventListener('hidden.bs.toast', () => el.remove());
}

/* ---------------------------------------------------------------------------
 * Navbar shadow on scroll
 * --------------------------------------------------------------------------- */
function initNavbarScroll() {
  const navbar = document.getElementById('main-navbar');
  if (!navbar) return;
  const onScroll = () => navbar.classList.toggle('scrolled', window.scrollY > 10);
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
}

/* ---------------------------------------------------------------------------
 * Toasts rendered from Django messages (already in the HTML)
 * --------------------------------------------------------------------------- */
function initMessageToasts() {
  document.querySelectorAll('#toast-container .toast').forEach((el) => {
    const delay = parseInt(el.dataset.delay || '4200', 10);
    setTimeout(() => {
      const toast = bootstrap.Toast.getInstance(el) || new bootstrap.Toast(el);
      toast.hide();
    }, delay);
  });
}

/* ---------------------------------------------------------------------------
 * Cart badge
 * --------------------------------------------------------------------------- */
function updateCartBadge(count) {
  const badge = document.getElementById('cart-count');
  if (!badge) return;
  badge.textContent = count;
  badge.classList.toggle('d-none', count <= 0);
  badge.classList.remove('pop');
  void badge.offsetWidth;          // restart the CSS animation
  badge.classList.add('pop');
}

/* ---------------------------------------------------------------------------
 * Add-to-cart forms (cards + product detail)
 * --------------------------------------------------------------------------- */
function initAddToCart() {
  document.querySelectorAll('form[data-cart-add]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      if (button) button.disabled = true;   // prevent double-clicks

      const result = await postForm(form.action, new FormData(form));
      const message = result.data && result.data.message;

      if (result.ok) {
        ssToast(message, 'success');
        updateCartBadge(result.data.cart_count || 0);
        const qty = form.querySelector('input[name="quantity"]');
        if (qty) qty.value = 1;             // reset the stepper
        // PHASE 17: brief "Added" confirmation on the button itself
        // (flashButtonAdded re-enables it when the flash ends).
        flashButtonAdded(button);
      } else {
        ssToast(message || 'Could not add to cart.', 'error');
        if (button) button.disabled = false;
      }
    });
  });
}

/* ---------------------------------------------------------------------------
 * Quantity steppers (detail page) + clamp all qty inputs
 * --------------------------------------------------------------------------- */
function initQuantitySteppers() {
  document.querySelectorAll('.qty-selector').forEach((wrap) => {
    const input = wrap.querySelector('input');
    if (!input) return;

    const clamp = () => {
      const min = parseInt(input.min || '1', 10);
      const max = parseInt(input.max || '999', 10);
      let value = parseInt(input.value, 10);
      if (Number.isNaN(value)) value = min;
      input.value = Math.min(Math.max(value, min), max);
    };

    wrap.querySelectorAll('button[data-step]').forEach((button) => {
      button.addEventListener('click', () => {
        const step = parseInt(button.dataset.step, 10);
        let value = parseInt(input.value || input.min || '1', 10);
        if (Number.isNaN(value)) value = 1;
        input.value = value + step;
        clamp();
      });
    });
    input.addEventListener('change', clamp);
    clamp();
  });
}

/* ---------------------------------------------------------------------------
 * Wishlist toggle buttons
 * --------------------------------------------------------------------------- */
function initWishlistToggle() {
  document.querySelectorAll('[data-wishlist-toggle]').forEach((button) => {
    button.addEventListener('click', async () => {
      const productId = button.dataset.productId;
      const slug = button.dataset.productSlug || '';
      const next = `/product/${slug}/`;

      button.disabled = true;
      const result = await postForm(`/wishlist/toggle/${productId}/`, { next });
      button.disabled = false;

      if (result.ok && result.data) {
        // The logged-in response flips the icon on THIS button.
        button.classList.toggle('active', result.data.in_wishlist);
        const icon = button.querySelector('i');
        if (icon) icon.className = result.data.in_wishlist
          ? 'bi bi-heart-fill' : 'bi bi-heart';
        if (icon && button.classList.contains('btn-ss-ghost')) {
          icon.className = result.data.in_wishlist
            ? 'bi bi-heart-fill me-1' : 'bi bi-heart me-1';
        }
        ssToast(result.data.message, 'success');
      } else {
        // Not logged in: postForm got a 302/HTML. Tell the user plainly.
        ssToast('Please log in to use your wishlist.', 'info');
        const target = new URL(result.data && result.data.url || '/accounts/login/', window.location.origin);
        if (!target.searchParams.get('next')) {
          target.searchParams.set('next', window.location.pathname);
        }
        window.location.href = target.toString();
      }
    });
  });
}

/* ---------------------------------------------------------------------------
 * Newsletter form (footer)
 * --------------------------------------------------------------------------- */
function initNewsletter() {
  document.querySelectorAll('form[data-newsletter]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const result = await postForm(form.action, new FormData(form));
      const message = result.data && result.data.message;
      if (result.ok) {
        ssToast(message, 'success');
        form.reset();
      } else {
        ssToast(message || 'Please enter a valid email address.', 'error');
      }
    });
  });
}

/* ---------------------------------------------------------------------------
 * Reveal-on-scroll (subtle fade/slide-in for .reveal elements)
 * --------------------------------------------------------------------------- */
function initReveal() {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const elements = document.querySelectorAll('.reveal');
  if (reduceMotion || !('IntersectionObserver' in window)) {
    elements.forEach((el) => el.classList.add('visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target);   // animate once
      }
    });
  }, { threshold: 0.08 });
  elements.forEach((el) => observer.observe(el));
}

/* ---------------------------------------------------------------------------
 * 8. Wishlist page — remove / move-to-cart without a reload.
 *     Without JS the same <form>s submit classically and redirect back.
 * --------------------------------------------------------------------------- */
function refreshWishlistState(count) {
  const grid = document.getElementById('wish-grid');
  const empty = document.getElementById('wish-empty');
  const label = document.getElementById('wish-count');
  if (!grid || !empty) return;
  if (count === 0) {
    grid.style.display = 'none';
    empty.classList.remove('d-none');
    empty.classList.add('reveal', 'visible');
    if (label) label.textContent = 'Your wishlist is empty.';
  } else if (label) {
    label.textContent = count + (count === 1 ? ' item saved for later.'
                                             : ' items saved for later.');
  }
}

function initWishlistPage() {
  // "Remove" rows
  document.querySelectorAll('form[data-wish-remove]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const row = form.closest('[data-wish-row]');
      const result = await postForm(form.action, new FormData(form));
      if (result.ok && result.data) {
        ssToast(result.data.message, 'success');
        if (row) row.remove();
        refreshWishlistState(result.data.wishlist_count ?? 0);
      } else {
        ssToast((result.data && result.data.message) || 'Could not remove item.', 'error');
      }
    });
  });

  // "Move to cart" rows
  document.querySelectorAll('form[data-wish-move]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const row = form.closest('[data-wish-row]');
      const button = form.querySelector('[type="submit"]');
      if (button) button.disabled = true;   // prevent double-clicks

      const result = await postForm(form.action, new FormData(form));
      if (button) button.disabled = false;

      if (result.ok && result.data) {
        ssToast(result.data.message, 'success');
        updateCartBadge(result.data.cart_count || 0);
        if (row) row.remove();
        refreshWishlistState(result.data.wishlist_count ?? 0);
      } else {
        ssToast((result.data && result.data.message) || 'Could not move to cart.', 'error');
      }
    });
  });
}

/* ---------------------------------------------------------------------------
 * 9. Cart page — quantity steppers + live totals.
 *    With JS: changing a quantity fetches the update and patches the
 *    line total, the order summary and the free-shipping bar in place.
 *    Without JS: the same <form> submits classically and redirects back.
 * --------------------------------------------------------------------------- */
function applyCartTotals(totals, extra) {
  const set = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  if (totals) {
    set('cart-subtotal', '₹' + totals.subtotal);
    if (totals.discount && totals.discount !== '0.00') {
      set('cart-discount', '−₹' + totals.discount);
    }
    set('cart-shipping', totals.shipping === '0.00' ? 'FREE' : '₹' + totals.shipping);
    set('cart-tax', '₹' + totals.tax);
    set('cart-grand', '₹' + totals.grand_total);
  }
  const label = document.getElementById('free-ship-label');
  const fill = document.getElementById('free-ship-fill');
  const wrap = document.getElementById('free-ship');
  if (label && wrap && extra) {
    if (parseFloat(extra.free_shipping_remaining) === 0) {
      wrap.classList.add('free-ship--done');
      label.innerHTML = '<i class="bi bi-truck me-1"></i>You\'ve unlocked FREE shipping!';
      if (fill) fill.style.width = '100%';
    } else {
      wrap.classList.remove('free-ship--done');
      label.innerHTML =
        'Add <strong>₹' + extra.free_shipping_remaining +
        '</strong> more for FREE shipping';
      if (fill) fill.style.width = (extra.free_shipping_percent || 0) + '%';
    }
  }
}

function initCartUpdates() {
  document.querySelectorAll('form[data-cart-update]').forEach((form) => {
    const row = form.closest('[data-cart-row]');
    const input = form.querySelector('input[name="quantity"]');
    if (!input || !row) return;

    const clamp = () => {
      const min = parseInt(input.min || '1', 10);
      const max = parseInt(input.max || '999', 10);
      let value = parseInt(input.value, 10);
      if (Number.isNaN(value)) value = min;
      input.value = Math.min(Math.max(value, min), max);
    };

    // The +/− steppers change the input, then trigger the (intercepted) submit.
    form.querySelectorAll('button[data-cart-step]').forEach((button) => {
      button.addEventListener('click', () => {
        const step = parseInt(button.dataset.cartStep, 10);
        let value = parseInt(input.value || input.min || '1', 10);
        if (Number.isNaN(value)) value = 1;
        input.value = value + step;
        clamp();
        if (typeof form.requestSubmit === 'function') {
          form.requestSubmit();
        } else {
          form.querySelector('[type="submit"]').click();
        }
      });
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      clamp();
      const previous = input.value;
      const buttons = form.querySelectorAll('button');
      buttons.forEach((b) => (b.disabled = true));

      const result = await postForm(form.action, new FormData(form));
      buttons.forEach((b) => (b.disabled = false));

      if (result.ok && result.data) {
        updateCartBadge(result.data.cart_count || 0);
        const lineTotal = row.querySelector('[data-line-total]');
        if (lineTotal) lineTotal.textContent = '₹' + result.data.line_total;
        const unit = row.querySelector('[data-unit-price]');
        if (unit && result.data.unit_price) {
          unit.textContent = '₹' + result.data.unit_price + ' each';
        }
        if (result.data.max_qty) input.max = result.data.max_qty;
        applyCartTotals(result.data.totals, result.data);
      } else {
        ssToast((result.data && result.data.message) || 'Could not update the cart.', 'error');
        input.value = previous;   // revert on rejection (e.g. too many in stock)
      }
    });
  });
}

/* ---------------------------------------------------------------------------
 * 10. Product gallery — click a thumbnail to swap the main image.
 *    Without JS the thumbnails simply stay visible under the photo.
 * --------------------------------------------------------------------------- */
function initGallery() {
  const main = document.getElementById('gallery-main');
  const thumbs = document.querySelectorAll('.gallery-thumb');
  if (!main || thumbs.length === 0) return;

  thumbs.forEach((thumb) => {
    thumb.addEventListener('click', () => {
      main.src = thumb.dataset.full;
      main.alt = thumb.dataset.alt;
      thumbs.forEach((t) => t.classList.remove('active'));
      thumb.classList.add('active');
    });
  });
}

/* ---------------------------------------------------------------------------
 * 11. Search suggestions (PHASE 16) — live suggestions in the navbar box.
 *     Progressive enhancement: the box is a plain GET form, so with JS
 *     OFF (or if the fetch fails) everything works exactly as before.
 * --------------------------------------------------------------------------- */
async function initSearchSuggest() {
  const inputs = document.querySelectorAll('.js-search-input');
  if (!inputs.length) return;

  inputs.forEach((input) => {
    let box = null;        // <div> holding the suggestion list
    let timer = null;      // debounce handle (200 ms)
    let items = [];        // current suggestions
    let active = -1;       // index highlighted with the arrow keys

    function hide() {
      if (box) box.style.display = 'none';
      active = -1;
      input.setAttribute('aria-expanded', 'false');
    }

    function highlight(i) {
      active = i;
      Array.from(box.children).forEach((el, j) =>
        el.classList.toggle('search-suggest__item--active', j === i));
    }

    function render(results) {
      if (!results.length) return hide();
      items = results;
      active = -1;
      if (!box) {
        box = document.createElement('div');
        box.className = 'search-suggest';
        box.setAttribute('role', 'listbox');
        input.form.appendChild(box);
      }
      box.innerHTML = '';
      results.forEach((r, i) => {
        const a = document.createElement('a');
        a.href = r.url;
        a.className = 'search-suggest__item';
        a.setAttribute('role', 'option');

        const media = document.createElement(r.image ? 'img' : 'i');
        if (r.image) {
          media.src = r.image;
          media.alt = '';
          media.loading = 'lazy';
        } else {
          media.className = 'bi bi-bag';
        }

        const name = document.createElement('span');
        name.className = 'search-suggest__name';
        name.textContent = r.name;             // textContent: no HTML ever

        const price = document.createElement('span');
        price.className = 'search-suggest__price';
        price.textContent = '\u20b9' + r.price;

        a.append(media, name, price);
        a.addEventListener('mousemove', () => highlight(i));
        box.appendChild(a);
      });
      box.style.display = 'block';
      input.setAttribute('aria-expanded', 'true');
    }

    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) return hide();
      timer = setTimeout(async () => {
        try {
          const res = await fetch('/search/suggest/?q=' + encodeURIComponent(q));
          if (!res.ok) return hide();
          render((await res.json()).results);
        } catch (e) {
          hide();   // offline / blocked -> behave like a normal input
        }
      }, 200);
    });

    input.addEventListener('keydown', (e) => {
      if (!box || box.style.display === 'none' || !items.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        highlight((active + 1) % items.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        highlight((active - 1 + items.length) % items.length);
      } else if (e.key === 'Enter' && active >= 0) {
        e.preventDefault();          // go to the highlighted product
        window.location = items[active].url;
      } else if (e.key === 'Escape') {
        hide();
      }
      // Enter with nothing highlighted -> the form submits normally.
    });

    document.addEventListener('click', (e) => {
      if (!input.form.contains(e.target)) hide();
    });
  });
}

/* ---------------------------------------------------------------------------
 * 11b. Add-to-cart button feedback (PHASE 17) — briefly show "Added"
 *      so the customer gets confirmation right where they clicked.
 * --------------------------------------------------------------------------- */
function flashButtonAdded(button) {
  if (!button) return;
  const original = button.innerHTML;
  button.innerHTML = '<i class="bi bi-check-lg me-1"></i>Added';
  button.classList.add('btn-added');
  button.disabled = true;                   // ignore re-clicks while it shows
  setTimeout(() => {
    button.innerHTML = original;
    button.classList.remove('btn-added');
    button.disabled = false;
  }, 1100);
}

/* ---------------------------------------------------------------------------
 * 12. Image fade-in (PHASE 17) — product photos fade in when the file
 *     finishes loading. The hidden state lives in CSS behind
 *     html:not(.no-js), so visitors without JavaScript always see the
 *     image immediately (and the safety sweep below guarantees we can
 *     never leave a photo stuck invisible).
 * --------------------------------------------------------------------------- */
function initImageFade() {
  const imgs = document.querySelectorAll(
    '.product-card__media img, .detail-media img, ' +
    '.cart-line__media img, .order-row__items img, .gallery-thumb img');
  if (!imgs.length) return;

  const reveal = (img) => img.classList.add('in');

  imgs.forEach((img) => {
    img.classList.add('fade-load');         // arm the CSS hidden state…
    if (img.complete) {                     // …then lift it (cached images)
      reveal(img);
      return;
    }
    img.addEventListener('load', () => reveal(img), { once: true });
    img.addEventListener('error', () => reveal(img), { once: true });
  });

  // Safety sweep: anything still hidden after 2.5 s gets shown anyway.
  setTimeout(() => {
    document.querySelectorAll('.fade-load:not(.in)')
      .forEach((img) => img.classList.add('in'));
  }, 2500);
}

/* ---------------------------------------------------------------------------
 * Boot
 * --------------------------------------------------------------------------- */
document.addEventListener('DOMContentLoaded', () => {
  // Mark <html> so CSS can fall back gracefully when JS is available.
  document.documentElement.classList.remove('no-js');
  initNavbarScroll();
  initMessageToasts();
  initAddToCart();
  initQuantitySteppers();
  initWishlistToggle();
  initNewsletter();
  initWishlistPage();
  initCartUpdates();
  initGallery();
  initSearchSuggest();
  initImageFade();
  initReveal();
});
