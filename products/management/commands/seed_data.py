"""
Management command:  python manage.py seed_data

Populates the store with realistic sample data so the website never looks
empty while you develop:

    7 categories · 7 brands · 18 products · 3 coupons
    (+ one demo customer:  demo / Demo@1234)

Each product gets a generated placeholder photo (a soft gradient tile with
the product name) saved under media/products/seed/. Replace these with real
photos from the admin whenever you like — the command never touches photos
that already exist.

Usage:
    python manage.py seed_data                 # seed (idempotent: skips what exists)
    python manage.py seed_data --flush         # wipe sample data first, then seed
    python manage.py seed_data --refresh-images
                                               # recreate any MISSING seed photos
                                               # (after deleting media/products/seed/)

The command is SAFE to run repeatedly: it matches on names/slugs and only
creates records that are missing.
"""

from decimal import Decimal

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

# NOTE: management commands are loaded as top-level modules, so use
# ABSOLUTE imports here (a relative `from .models import ...` breaks).
from products.models import Brand, Category, Coupon, Product, ProductImage


# (name, category, brand, price, discount_price, stock, featured, short, description)
PRODUCTS = [
    # ---------------- Electronics ----------------
    (
        'Aurora Wireless Headphones', 'Electronics', 'Volt',
        '12999', '8999', 25, True,
        'Over-ear ANC headphones with 40h battery.',
        'Immersive sound with adaptive active noise cancellation, '
        '40-hour battery life, plush memory-foam earcups and multipoint '
        'Bluetooth 5.3. Foldable design with a premium hard case.',
    ),
    (
        'Pulse Smart Watch Series 5', 'Electronics', 'Volt',
        '9999', '7499', 30, True,
        'AMOLED smart watch with SpO2 and ECG.',
        '1.43" always-on AMOLED display, heart-rate, SpO2 and ECG '
        'sensors, 120+ sport modes, 5 ATM water resistance and up to '
        '10 days of battery on a single charge.',
    ),
    (
        'Nimbus 14" Ultrabook', 'Electronics', 'Skyline',
        '64999', '57999', 12, True,
        '14" ultrabook, 16GB RAM, 512GB SSD.',
        'Feather-light 1.2kg aluminium chassis, 14" 2.2K 90Hz display, '
        '16GB LPDDR5 RAM, 512GB NVMe SSD and all-day battery. Ships '
        'with a 1-year on-site warranty.',
    ),
    (
        'Echo Smart Speaker', 'Electronics', 'Volt',
        '4999', '3499', 40, False,
        '360° room-filling smart speaker.',
        '360° sound with deep bass, built-in voice assistant, '
        'multi-room pairing and a fabric-wrapped premium finish.',
    ),
    # ---------------- Fashion ----------------
    (
        'Everyday Cotton T-Shirt', 'Fashion', 'Urban Threads',
        '599', '399', 200, False,
        '100% combed cotton, regular fit.',
        'Buttery-soft 100% combed cotton, pre-shrunk and bio-washed '
        'for lasting comfort. Regular fit with a ribbed crew neck. '
        'Available in a range of earthy tones.',
    ),
    (
        'Slim Fit Denim Jeans', 'Fashion', 'Urban Threads',
        '2499', '1799', 120, True,
        'Stretch denim, slim tapered fit.',
        'Premium stretch denim with a slim tapered cut, four-pocket '
        'styling and a button fly. Fades beautifully with wear.',
    ),
    (
        'Waterproof Bomber Jacket', 'Fashion', 'Northwind',
        '4999', '3499', 60, False,
        '3-layer waterproof bomber, -10°C ready.',
        'Three-layer waterproof and windproof shell with a sealed '
        'zip, adjustable cuffs and a packable hood. Ready for winter '
        'commutes and mountain days.',
    ),
    # ---------------- Shoes ----------------
    (
        'Velocity Running Shoes', 'Shoes', 'Stride',
        '3999', '2799', 80, True,
        'Responsive foam runners, 8mm drop.',
        'Responsive nitrogen-infused midsole, breathable engineered '
        'mesh and a grippy rubber outsole. Built for daily miles and '
        'race day alike.',
    ),
    (
        'Court Classic Sneakers', 'Shoes', 'Stride',
        '2999', '2199', 90, False,
        'Minimal leather court sneakers.',
        'Clean minimalist silhouette in full-grain leather with a '
        'cushioned insole and a vintage-inspired gum sole. Pairs with '
        'everything.',
    ),
    # ---------------- Accessories ----------------
    (
        'Aviator Polarized Sunglasses', 'Accessories', 'Northwind',
        '1999', '1299', 100, False,
        'Polarized UV400 aviators, metal frame.',
        'Classic aviator frame in brushed metal with polarized UV400 '
        'lenses, a hard case and a microfibre cleaning cloth.',
    ),
    (
        'Everyday Canvas Backpack', 'Accessories', 'Urban Threads',
        '2499', '1699', 70, True,
        '20L water-repellent canvas backpack.',
        '20L capacity with a padded 15.6" laptop sleeve, water-repellent '
        'waxed canvas, leather trim and hidden anti-theft pocket.',
    ),
    # ---------------- Home & Furniture ----------------
    (
        'Ergonomic Task Chair', 'Home & Furniture', 'Haven',
        '8999', '6999', 20, True,
        'Breathable mesh, 4D armrests.',
        'Breathable mesh back, 4D adjustable armrests, lumbar support '
        'and a tilt-lock mechanism. Certified to support 8+ hours a day.',
    ),
    (
        'Oak Extendable Dining Table', 'Home & Furniture', 'Haven',
        '18999', '14999', 8, False,
        'Solid oak table, seats 4–6.',
        'Solid oak top with a dovetail butterfly extension that seats '
        'four to six. Finished with a food-safe natural oil.',
    ),
    (
        'Linen Throw Cushion (Set of 2)', 'Home & Furniture', 'Haven',
        '999', '699', 150, False,
        'Stonewashed linen cushions, 45×45.',
        'Stonewashed European linen with a concealed zip and feather '
        'inserts. Gets softer with every wash.',
    ),
    # ---------------- Beauty ----------------
    (
        'Hydra Glow Vitamin C Serum', 'Beauty', 'Botanica',
        '899', '599', 180, True,
        '15% vitamin C, brightening serum.',
        '15% ethylated vitamin C with hyaluronic acid and vitamin E '
        'to brighten, hydrate and even skin tone. Fragrance-free and '
        'dermatologically tested.',
    ),
    (
        'Ceramide Repair Moisturizer', 'Beauty', 'Botanica',
        '699', '499', 160, False,
        '48h hydration, ceramide barrier cream.',
        'A weightless daily moisturizer with ceramides and squalane '
        'that restores the skin barrier and locks in 48 hours of '
        'hydration. Suitable for all skin types.',
    ),
    # ---------------- Sports ----------------
    (
        'Pro Performance Football', 'Sports', 'Stride',
        '1499', '999', 60, False,
        'FIFA-quality thermo-bonded football.',
        'Thermo-bonded panels for a true flight, all-weather grip '
        'pattern and a butyl bladder that keeps air for weeks.',
    ),
    (
        'Yoga Mat Pro (6mm)', 'Sports', 'Haven',
        '1299', '899', 120, False,
        '6mm non-slip mat with strap.',
        '6mm cushioned TPE surface with dual-texture grip, alignment '
        'prints and a carry strap. Latex-free and easy to clean.',
    ),
]

# (code, type, value, min_order, max_discount, usage_limit, days_valid)
COUPONS = [
    ('WELCOME10', 'percentage', '10', '0', None, 1000, 365),
    ('SAVE500', 'fixed', '500', '4999', None, 500, 90),
    ('FLAT20', 'percentage', '20', '9999', '2000', 200, 60),
]

# Brand taglines (name -> description)
BRANDS = {
    'Volt': 'Consumer electronics and audio, engineered for everyday life.',
    'Skyline': 'Lightweight performance laptops for creators on the move.',
    'Urban Threads': 'Everyday apparel cut from honest, durable fabrics.',
    'Northwind': 'Technical outdoor wear built for the elements.',
    'Stride': 'Footwear and sportswear designed to move with you.',
    'Haven': 'Furniture and home essentials with a calm, lasting design.',
    'Botanica': 'Clean, plant-powered skincare for real results.',
}

# Category descriptions (name -> description)
CATEGORIES = {
    'Electronics': 'Headphones, smart watches, laptops and smart home tech.',
    'Fashion': 'T-shirts, denim and outerwear for every day.',
    'Shoes': 'Runners, sneakers and everything in between.',
    'Accessories': 'Sunglasses, bags and the finishing touches.',
    'Home & Furniture': 'Chairs, tables and soft goods for a calmer home.',
    'Beauty': 'Serums and skincare for glowing, healthy skin.',
    'Sports': 'Gear for the pitch, the studio and the trail.',
}

# A palette of (top, bottom) gradient colours per category for the
# generated placeholder photos.
CATEGORY_COLORS = {
    'Electronics': (67, 56, 202),
    'Fashion': (190, 24, 93),
    'Shoes': (5, 150, 105),
    'Accessories': (217, 119, 6),
    'Home & Furniture': (13, 148, 136),
    'Beauty': (219, 39, 119),
    'Sports': (37, 99, 235),
}


def make_placeholder(path, title, rgb):
    """Create a 900x900 gradient tile with the product name centred."""
    width = height = 900
    top, bottom = (rgb, rgb)
    img = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(img)
    # Vertical gradient
    for y in range(height):
        t = y / height
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        # Lighten toward the top for depth
        lift = int(40 * (1 - t))
        draw.line([(0, y), (width, y)], fill=(
            min(255, r + lift), min(255, g + lift), min(255, b + lift)
        ))
    # Soft vignette circle
    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.ellipse([150, 150, 750, 750], fill=(255, 255, 255, 26))
    img = Image.alpha_composite(img.convert('RGBA'), overlay).convert('RGB')
    draw = ImageDraw.Draw(img)

    # Use the fonts BUNDLED with the project (products/fonts/) via an
    # absolute path. This matters: on a plain Windows machine there is
    # no DejaVu installed, so loading by bare filename would fall back
    # to Pillow's 10px bitmap font and the product name would be
    # invisible on a 900px tile.
    fonts_dir = Path(__file__).resolve().parents[2] / 'fonts'
    try:
        font = ImageFont.truetype(str(fonts_dir / 'DejaVuSans-Bold.ttf'), 64)
        small = ImageFont.truetype(str(fonts_dir / 'DejaVuSans.ttf'), 30)
    except OSError:
        font = ImageFont.load_default()
        small = font

    # Wrap the title to at most two lines
    words = title.split()
    lines, line = [], ''
    for w in words:
        if draw.textlength(line + ' ' + w, font=font) > 720 and line:
            lines.append(line)
            line = w
        else:
            line = f'{line} {w}'.strip()
    lines.append(line)
    lines = lines[:2]

    block_h = len(lines) * 54
    y = (height - block_h) // 2
    for ln in lines:
        w = draw.textlength(ln, font=font)
        draw.text(((width - w) / 2, y), ln, font=font, fill=(255, 255, 255, 235))
        y += 54
    # Small "SHOPSHERE SAMPLE" caption
    cap = 'SHOPSHERE  ·  SAMPLE PRODUCT'
    cw = draw.textlength(cap, font=small)
    draw.text(((width - cw) / 2, y + 20), cap, font=small,
              fill=(255, 255, 255, 180))

    img.save(path, 'JPEG', quality=82)


class Command(BaseCommand):
    help = 'Seed the store with realistic sample categories, products and coupons.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Delete previously seeded sample data before re-seeding.',
        )
        parser.add_argument(
            '--refresh-images', action='store_true',
            help="Regenerate the seeded placeholder photos when their files "
                 "are missing on disk (e.g. after deleting media/products/seed/). "
                 "Real photos uploaded via the admin are never touched.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options['flush']:
            self._flush()

        cats_created = self._seed_categories()
        brands_created = self._seed_brands()
        products_created = self._seed_products(
            refresh_images=options['refresh_images'])
        coupons_created = self._seed_coupons()
        demo_created = self._seed_demo_customer()

        self.stdout.write(self.style.SUCCESS('✔ Seed data complete.'))
        self.stdout.write(
            f'  Categories : {cats_created} created '
            f'({Category.objects.count()} total)'
        )
        self.stdout.write(
            f'  Brands     : {brands_created} created '
            f'({Brand.objects.count()} total)'
        )
        self.stdout.write(
            f'  Products   : {products_created} created '
            f'({Product.objects.count()} total)'
        )
        self.stdout.write(
            f'  Coupons    : {coupons_created} created '
            f'({Coupon.objects.count()} total)'
        )
        if demo_created:
            self.stdout.write(
                "  Demo login : username 'demo', password 'Demo@1234' "
                '(regular customer, not a superuser)'
            )

    # ------------------------- helpers ------------------------------
    def _flush(self):
        if not (Product.objects.exists() or Category.objects.exists()):
            self.stdout.write('Nothing to flush.')
            return
        # Deleting categories cascades to their products, which cascades
        # to gallery images / reviews / wishlist items.
        Category.objects.all().delete()
        Brand.objects.all().delete()
        Coupon.objects.all().delete()
        self.stdout.write('Flushed existing sample data.')

    def _seed_categories(self):
        created = 0
        for name, description in CATEGORIES.items():
            _, was_created = Category.objects.get_or_create(
                name=name, defaults={'description': description}
            )
            created += was_created
        return created

    def _seed_brands(self):
        created = 0
        for name, description in BRANDS.items():
            _, was_created = Brand.objects.get_or_create(
                name=name, defaults={'description': description}
            )
            created += was_created
        return created

    def _seed_products(self, refresh_images=False):
        from django.conf import settings
        seed_dir = settings.MEDIA_ROOT / 'products' / 'seed'
        seed_dir.mkdir(parents=True, exist_ok=True)

        created = 0
        for (name, cat_name, brand_name, price, discount, stock,
             featured, short, description) in PRODUCTS:
            category = Category.objects.get(name=cat_name)
            brand = Brand.objects.get(name=brand_name)
            rgb = CATEGORY_COLORS.get(cat_name, (67, 56, 202))

            existing = Product.objects.filter(name=name).first()
            if existing:
                product = existing   # idempotent: reuse, then backfill gallery
                if refresh_images and product.image:
                    image_path = settings.MEDIA_ROOT / product.image.name
                    if not image_path.exists():
                        make_placeholder(str(image_path), name, rgb)
                self._seed_gallery(product, seed_dir, rgb, refresh_images)
                continue

            # Placeholder photo (only generated once, on first seed).
            # slugify() keeps the filename valid on EVERY operating
            # system — Windows forbids characters like " < > / in file
            # names, so a plain .replace(' ', '_') is not enough
            # (e.g. the product 'Nimbus 14" Ultrabook').
            image_field = f'products/seed/{slugify(name)}.jpg'
            image_path = settings.MEDIA_ROOT / image_field
            if not image_path.exists():
                make_placeholder(str(image_path), name, rgb)

            product = Product.objects.create(
                name=name,
                category=category,
                brand=brand,
                price=Decimal(price),
                discount_price=Decimal(discount) if discount else None,
                stock=stock,
                featured=featured,
                short_description=short,
                description=description,
                image=image_field,
            )
            created += 1
            self._seed_gallery(product, seed_dir, rgb)
        return created

    def _seed_gallery(self, product, seed_dir, rgb, refresh_images=False):
        """
        Give the product 2 extra gallery photos (darker + lighter tints of
        its category colour) so the detail-page gallery has something to
        show. Idempotent: skipped if the product already has gallery images
        (unless refresh_images is set — then missing files are recreated).
        """
        if product.images.exists():
            if refresh_images:
                slug = slugify(product.name)
                for (tint, label) in ((-50, 'detail'), (60, 'side')):
                    path = seed_dir / f'{slug}_{label}.jpg'
                    if not path.exists():
                        shaded = tuple(max(0, min(255, c + tint)) for c in rgb)
                        make_placeholder(str(path),
                                         f'{product.name} ({label} view)',
                                         shaded)
            return
        slug = slugify(product.name)
        for (tint, label) in ((-50, 'detail'), (60, 'side')):
            filename = f'{slug}_{label}.jpg'
            field = f'products/seed/{filename}'   # stored on the model
            path = seed_dir / filename            # on disk (seed_dir == MEDIA_ROOT/products/seed)
            if not path.exists():
                shaded = tuple(max(0, min(255, c + tint)) for c in rgb)
                make_placeholder(str(path), f'{product.name} ({label} view)', shaded)
            ProductImage.objects.create(
                product=product, image=field,
                alt_text=f'{product.name} — {label} view',
            )

    def _seed_demo_customer(self):
        """
        One regular (non-superuser) customer so you can log in and try
        the full store without registering:

            username: demo    password: Demo@1234

        Comes with one saved address (auto-becomes the default, so
        checkout can start immediately). Idempotent: skipped when the
        account already exists. Returns 1 if the account was created.
        """
        from django.contrib.auth.models import User
        from customers.models import Address

        demo = User.objects.filter(username='demo').first()
        if demo is None:
            # UserProfile is created automatically by the post_save signal.
            demo = User.objects.create_user(
                username='demo',
                email='demo@example.com',
                password='Demo@1234',
                first_name='Demo',
                last_name='Customer',
            )
            created = 1
        else:
            created = 0

        if not Address.objects.filter(user=demo).exists():
            Address.objects.create(
                user=demo,
                label='Home',
                full_name='Demo Customer',
                phone='9876543210',
                address_line_1='12 Lake Road',
                city='Anand',
                state='Gujarat',
                pincode='388001',
            )   # first saved address auto-becomes the default (Address.save)
        return created

    def _seed_coupons(self):
        from django.utils import timezone
        from datetime import timedelta

        created = 0
        for (code, dtype, value, min_order, max_disc, limit, days) in COUPONS:
            if Coupon.objects.filter(code=code).exists():
                continue
            Coupon.objects.create(
                code=code,
                discount_type=dtype,
                discount_value=Decimal(value),
                minimum_order_amount=Decimal(min_order),
                maximum_discount=Decimal(max_disc) if max_disc else None,
                usage_limit=limit,
                valid_to=timezone.now() + timedelta(days=days),
            )
            created += 1
        return created
