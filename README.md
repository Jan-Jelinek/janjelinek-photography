# Jelinek Photos

A minimalist, personal photography site to showcase some of my favorite shots.

Built with [Astro](https://astro.build/) and optimized for speed, responsiveness, and a great viewing experience across devices.

🌐 Live site: [jj.photography](https://jj.photography)

## Tech Stack

* [Astro](https://astro.build/) - Web framework
* [Tailwind CSS](https://tailwindcss.com/) - Styling
* [Photoswipe](https://photoswipe.com/) - Image galleries
* [GitHub Pages](https://pages.github.com) - Hosting
* [Cloudflare R2](https://www.cloudflare.com/developer-platform/products/r2/) - Image Hosting

## Features

- **Photography Collections via MDX**  
  Collections are written in MDX files for easy content management and organization.

- **Responsive Design**  
  Fully responsive layout, ensuring photos look great on desktop, tablet, and mobile devices.

- **Optimized Images**
  Uses srcset to serve appropriately sized images depending on the viewer’s screen resolution.

- **Interactive Galleries**  
  PhotoSwipe powers elegant fullscreen image galleries with zoom, swipe, and navigation controls.

- **Fast & Modern**
  Astro ensures minimal JavaScript and fast static site performance.

## Writing a Collection

Each collection is a folder in `src/collections/`, e.g. `src/collections/2025-asia/`, holding:
- **`post.mdx`**: everything about the page goes in its frontmatter (between the `---` lines). The text
  below the frontmatter is the intro shown next to the title.
- **`photos.json`**: the list of uploaded photos, written by the upload script. Don't edit it by hand.

Photos are exports you drop into the folder. The upload script sends them to the image host:
see [r2sync/README.md](r2sync/README.md).

```yaml
---
sequence: 3                     # order on the home page (highest first)
slug: 2025-asia                 # the URL: /collections/2025-asia (its year shows on the card)
title: Travel Log
place: Asia                     # optional, shown on the card and the page
cover: { photo: DSCF0396.JPG, zoom: 1.15 }
feature: [DSCF3628.JPG, DSCF8215.JPG]
auto-captions: true
rows:
- text: "Taiwan 🇹🇼"
- [DSCF0396.JPG]
- [DSCF1970.JPG, [DSCF1779.JPG, DSCF1847.JPG]]
- aside: [PXL_0001.jpg, "Lunch with a cat sleeping next to me."]
- text-f: ["Bunny Island.", Snapchat-1.jpg, clip.mp4]
captions:
  DSCF0396.JPG: { text: "Jiufen at dusk" }
---

The intro, in Markdown.
```

`#` starts a comment, handy for labelling sections of `rows`.

### Rows

`rows` is the gallery, top to bottom. Each entry is a photo row, a text section or an aside.

| Row | What it does |
|---|---|
| `- [A.jpg]` | One photo, full width. |
| `- [A.jpg, B.jpg, C.jpg]` | Photos side by side, sized so the row lines up. |
| `- [A.jpg, [B.jpg, C.jpg]]` | A nested list stacks photos in one column: A on the left, B above C on the right. |
| `- text: "…"` | Text on the left, at most 640px wide. |
| `- text-r: "…"` | The same, on the right and right-aligned. |
| `- text-f: "…"` | Text using the full width. |
| `- aside: "…"` | A note beside the photo row above it. See [Asides](#asides). |

### Snapshots in text sections

A text section can be a list mixing paragraphs with images and videos:

```yaml
- text: ["First paragraph.", PXL_0001.jpg, PXL_0002.jpg, "Another paragraph."]
```

- Each string is one paragraph, unless it has no spaces and ends in a photo extension (`.jpg`,
  `.png`, `.webp`, …). Then it's an image.
- Consecutive images form a strip of up to 4 on one line, with "+N" when there are more. In asides
  they form a grid of 2×2 at most.
- Snapshots open in their own small lightbox, separate from the main gallery.
- **Videos** (`.mp4`, `.mov`, `.m4v`) show a still with a ▶ button and play with sound in the
  lightbox. They never autoplay. Videos only go in text sections and asides, not in photo rows.

### Asides

An aside is a short story beside a photo row: phone snaps, behind-the-scenes, anecdotes. Put it
**right after the photo row** it belongs to:

```yaml
- [DSCF2598.JPG, DSCF2517.JPG]
- aside: [PXL_0001.jpg, "If you cross the glacier, you get to walk on the moon."]
```

- It takes the same mix of text, images and videos as a text section.
- It sits in the margin on wide screens and under the row on smaller ones. Long asides get a
  "Read more" button.
- Asides are numbered in order down the page. The number badge goes on the row's top-right photo.
- **`aside-N:`** puts the badge on the row's Nth photo instead, counting in reading order with stacks
  included. In `[A, [B, C, D]]`, `aside-1` is A and `aside-4` is D.
- A row can have several asides: list them one after another.

### Captions

```yaml
auto-captions: true
captions:
  DSCF0396.JPG: { text: "Jiufen at dusk" }
  DSCF2560.JPG: { exposure: "f/8 · 1/250s · ISO 160" }
```

- `text` shows under the photo and doubles as its alt text for screen readers.
- `exposure` shows under the photo and in the lightbox.
- `auto-captions: true` fills in the exposure from each photo's camera data, shown in the lightbox
  only. A hand-written `exposure` still wins.

### Home page

| Field | What it does |
|---|---|
| `cover` | The collection's square thumbnail. Must be a photo in `rows`. `cover: DSCF0396.JPG` crops the centre. `cover: { photo: DSCF0396.JPG, zoom: 1.15, x: 50, y: 30 }` zooms in (1 = the biggest square that fits), and `x` / `y` (0–100) set the point of the photo at the square's centre. |
| `feature` | Photos the big hero image may show. Each visit picks a random collection with `feature`, then one of its photos. They must be in `rows`. |
| `feature-test` | For trying out hero photos: while any post has it, `npm run dev` only shows those. The live site ignores it, and the build warns until you remove it. |

### Mistakes the build catches

The build stops with a message pointing at the line in `post.mdx` when:
- a photo or video isn't on your PC or uploaded;
- a caption, `cover`, `feature` or `feature-test` names a photo that isn't in `rows`;
- an aside doesn't come right after a photo row, or `aside-N` asks for a photo the row doesn't have;
- a video is in a photo row.

## Development

### Prerequisites

- [Node.js](https://nodejs.org/) (latest LTS recommended)
- npm (or yarn)

### Getting Started

Clone the repo and install dependencies:

```
git clone https://github.com/Jan-Jelinek/janjelinek-photography.git
cd janjelinek-photography
npm install
```

Run the development server:

```
npm run dev
```

Build for production:
```
npm run build
```

Preview the production build:
```
npm run preview
```

## Contact

Jan Jelinek - [janjelinek.dev@gmail.com](mailto:janjelinek.dev@gmail.com)

Project Link: [https://github.com/Jan-Jelinek/janjelinek-photography](https://github.com/Jan-Jelinek/janjelinek-photography)

## License

[MIT](https://choosealicense.com/licenses/mit/)
