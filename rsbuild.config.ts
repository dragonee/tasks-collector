import { defineConfig } from '@rsbuild/core';
import { pluginVue2 } from '@rsbuild/plugin-vue2';
import { pluginSass } from '@rsbuild/plugin-sass';

export default defineConfig({
  plugins: [pluginVue2(), pluginSass()],

  source: {
    entry: {
      vendor: './tasks/assets/vendor.js',
      app: './tasks/assets/app.js',
      shared: './tasks/assets/scripts/shared.js',
      hello_world_mount: './tasks/assets/components/hello_world_mount.js',
    },
  },

  output: {
    distPath: {
      root: 'tasks/static/local',
      js: '.',
      css: '.',
      svg: 'assets/images',
      font: 'assets/fonts',
      image: 'assets/images',
      media: 'assets/images',
    },
    filename: {
      js: '[name].[contenthash].js',
      css: '[name].[contenthash].css',
    },
    assetPrefix: '/static/',
    cleanDistPath: true,
  },

  tools: {
    rspack: (config, { environment }) => {
      // Disable HTML plugin completely
      config.plugins = config.plugins.filter(
        plugin => plugin.constructor.name !== 'HtmlRspackPlugin'
      );

      config.optimization = {
        ...config.optimization,
        runtimeChunk: 'single',
      };

      config.plugins.push(
        // Generate manifest file compatible with webpack-assets-manifest
        {
          apply(compiler) {
            compiler.hooks.emit.tap('ManifestPlugin', (compilation) => {
              const manifest = {};

              // Generate manifest in the same format as webpack-assets-manifest
              for (const [name, asset] of Object.entries(compilation.assets)) {
                if (name.endsWith('.js') || name.endsWith('.css')) {
                  // Remove hash from key but keep full filename as value
                  const chunkName = name.replace(/\.[a-f0-9]+\./, '.');
                  manifest[chunkName] = name;
                }
              }

              const manifestContent = JSON.stringify(manifest, null, 2);
              const manifestPath = environment === 'dist'
                ? 'webpack-stats.dist.json'
                : 'webpack-stats.local.json';

              console.log(`[Rsbuild] Environment: ${environment}, generating manifest: ${manifestPath}`);

              const fs = require('fs');
              const path = require('path');
              fs.writeFileSync(path.resolve(manifestPath), manifestContent);
            });
          },
        }
      );

      return config;
    },
  },

  environments: {
    local: {
      output: {
        distPath: {
          root: 'tasks/static/local',
        },
      },
    },
    dist: {
      output: {
        distPath: {
          root: 'tasks/static/dist',
        },
      },
    },
  },
});
