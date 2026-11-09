import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const caption = z.object({
  text: z.string().optional(),
  exposure: z.string().optional(),
});

// A row is either a list of image IDs ("05v" = portrait) or a block of text.
// A nested list in a row stacks those photos into one column: ["A", ["B", "C"]].
// `text-r:` instead of `text:` puts the text on the right, right-aligned.
const row = z.union([
  z.array(z.union([z.string(), z.array(z.string()).min(2)])).min(1),
  z.object({ text: z.string() }),
  z.object({ 'text-r': z.string() }),
]);

// An aside next to a photo's row: "DSCF0727.JPG": ["story…", "Snapchat-1.jpg", ...], or just "story…".
// A string with no spaces ending in a photo extension is an image; anything else is text (one paragraph each).
const aside = z.union([z.string(), z.array(z.string()).min(1)]);

const stripPortrait = (id: string) => id.replace(/v$/, '');

const posts = defineCollection({
  loader: glob({ pattern: ['**/post.mdx'], base: 'src/collections' }),
  schema: ({ image }) => z.object({
      sequence: z.number(),
      slug: z.string(),
      title: z.string(),
      cover: image(),
      place: z.string().optional(),
      rows: z.array(row).min(1),
      // nullish: a `captions:` key with only comments under it parses as null.
      captions: z.record(z.string(), caption).nullish().transform((c) => c ?? {}),
      commentary: z.record(z.string(), aside).nullish().transform((c) => c ?? {}),
  }).superRefine((data, ctx) => {
      const ids = new Set(
        data.rows.flatMap((r) => (Array.isArray(r) ? r.flat().map(stripPortrait) : [])),
      );
      for (const [field, label] of [['captions', 'Caption'], ['commentary', 'Commentary']] as const) {
        for (const key of Object.keys(data[field])) {
          if (!ids.has(stripPortrait(key))) {
            ctx.addIssue({
              code: 'custom',
              path: [field, key],
              message: `${label} for "${key}", but no photo with that ID is in rows`,
            });
          }
        }
      }
  }),
});

export const collections = { posts };
