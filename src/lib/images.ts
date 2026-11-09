// Public R2 bucket holding the resized photos that `py r2sync` makes.
// Set PUBLIC_IMAGE_BASE (e.g. the bucket's r2.dev URL) to override, such as before the custom domain works.
export const IMAGE_BASE: string = import.meta.env.PUBLIC_IMAGE_BASE ?? "https://i.jelinekphotos.com";

export const publicUrl = (key: string) => `${IMAGE_BASE.replace(/\/$/, "")}/${key}`;
