import { defineConfig } from "vite";
import { resolve } from "path";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
    const isDevelopment = mode === "development";

    return {
        root: ".",
        base: isDevelopment ? "/" : "/static/dist/",
        plugins: [tailwindcss()],

        build: {
            manifest: true,
            outDir: "static/dist",
            emptyOutDir: true,
            sourcemap: isDevelopment,
            rollupOptions: {
                input: {
                    main: resolve(__dirname, "src/js/main.js"),
                },
            },
        },

        server: {
            port: 5173,
            host: "127.0.0.1",
            origin: "http://localhost:5173",
            cors: true,
            headers: {
                "Access-Control-Allow-Origin": "*",
            },
            watch: {
                ignored: ["**/.git/**", "**/staticfiles/**"],
            },
            fs: {
                allow: [".."],
            },
        },
    };
});
