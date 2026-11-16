import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const caption = z.object({
  text: z.string().optional(),
  exposure: z.string().optional(),
});

// A row is either a list of image IDs ("05v" = portrait) or a block of text.
// A nested list in a row stacks those photos into one column: ["A", ["B", "C"]].
// `text-r:` instead of `text:` puts the text on the right, right-aligned; `text-f:` uses the full width.
// Like asides, a text section can be a list mixing text and snapshot images (their own small lightbox).
// A string with no spaces ending in a photo extension is an image, in .mp4/.mov/.m4v a video (tap to play);
// anything else is text (one paragraph each).
const textItems = z.union([z.string(), z.array(z.string()).min(1)]);
const row = z.union([
  z.array(z.union([z.string(), z.array(z.string()).min(2)])).min(1),
  z.object({ text: textItems }),
  z.object({ 'text-r': textItems }),
  z.object({ 'text-f': textItems }),
  // An aside beside the photo row right above it: `- aside: ["story…", "Snapchat-1.jpg", ...]`.
  z.object({ aside: textItems }),
]);

// The home page thumbnail: a photo from rows, cropped to a square. `zoom` 1 = the biggest square that
// fits; `x`/`y` (0–100) = the point of the photo at the square's centre.
const cover = z
  .union([
    z.string(),
    z.object({
      photo: z.string(),
      zoom: z.number().min(1).default(1),
      x: z.number().min(0).max(100).default(50),
      y: z.number().min(0).max(100).default(50),
    }),
  ])
  .transform((c) => (typeof c === 'string' ? { photo: c, zoom: 1, x: 50, y: 50 } : c));

const stripPortrait = (id: string) => id.replace(/v$/, '');

const posts = defineCollection({
  loader: glob({ pattern: ['**/post.mdx'], base: 'src/collections' }),
  schema: z.object({
      sequence: z.number(),
      slug: z.string(),
      title: z.string(),
      cover,
      place: z.string().optional(),
      rows: z.array(row).min(1),
      // nullish: a `captions:` key with only comments under it parses as null.
      captions: z.record(z.string(), caption).nullish().transform((c) => c ?? {}),
      // Old format (asides keyed by photo, top level); asides now go inline in rows as `- aside:`. Only kept to point that out.
      commentary: z.unknown().optional(),
      // Photos from rows the home page hero may show (picked at random on each visit).
      feature: z.array(z.string()).min(1).optional(),
      // Show each photo's aperture · shutter · ISO under it (from the camera data). A caption's own
      // `exposure` still wins.
      'auto-captions': z.boolean().default(false),
  }).superRefine((data, ctx) => {
      const ids = new Set(
        data.rows.flatMap((r) => (Array.isArray(r) ? r.flat().map(stripPortrait) : [])),
      );
      for (const key of Object.keys(data.captions)) {
        if (!ids.has(stripPortrait(key))) {
          ctx.addIssue({
            code: 'custom',
            path: ['captions', key],
            message: `Caption for "${key}", but no photo with that ID is in rows`,
          });
        }
      }
      if (data.commentary != null) {
        ctx.addIssue({
          code: 'custom',
          path: ['commentary'],
          message: 'Asides now go in rows: put `- aside: [...]` right after the photo row it belongs to',
        });
      }
      // An aside row needs a photo row above it (other aside rows in between are fine).
      let photoRowAbove = false;
      data.rows.forEach((r, i) => {
        if (Array.isArray(r)) photoRowAbove = true;
        else if ('aside' in r) {
          if (!photoRowAbove) {
            ctx.addIssue({
              code: 'custom',
              path: ['rows', i],
              message: '`aside` must come right after a photo row (it sits beside that row)',
            });
          }
        } else photoRowAbove = false;
      });
      if (!ids.has(stripPortrait(data.cover.photo))) {
        ctx.addIssue({
          code: 'custom',
          path: ['cover'],
          message: `Cover "${data.cover.photo}" isn't a photo in rows`,
        });
      }
      (data.feature ?? []).forEach((name, i) => {
        if (!ids.has(stripPortrait(name))) {
          ctx.addIssue({
            code: 'custom',
            path: ['feature', i],
            message: `Feature "${name}" isn't a photo in rows`,
          });
        }
      });
  }),
});

export const collections = { posts };
