# WIP

A simple website for showcasing my photography.

Made with [Astro](https://astro.build/)

---

todo
- Finish PostThumbnail component
- Add next and previous post navigation buttons
- Customize Photoswipe (remove zoom button, look into what else i can do)
- Make ImageGallery auto-import images to posts using import.meta.glob()
- Favicon
- Fix up README
- Write posts
- Github actions and Hosting
- View transitions?
- View counter?

## Docker

```
docker build -t jj-p .
docker run -p 3001:80 jj-p
```

## Dependencies

[photoswipe](https://photoswipe.com/)

mdx

tailwind