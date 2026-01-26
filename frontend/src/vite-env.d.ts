/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_BUILD_DATE: string;
    readonly VITE_IMAGE_BUILD_DATE?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}

declare module "*.css" {
    const content: string;
    export default content;
}
