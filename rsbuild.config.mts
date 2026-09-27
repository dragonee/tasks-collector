import { defineConfig } from '@rsbuild/core';
import HtmlRspackPlugin from 'html-rspack-plugin';
import { pluginVue } from '@rsbuild/plugin-vue';
import { pluginSass } from '@rsbuild/plugin-sass';

export default defineConfig({
  plugins: [pluginVue(), pluginSass()],

  source: {
    entry: {
      app: './tasks/assets/app.js',
      hello_world_mount: './tasks/assets/components/hello_world_mount.js',
      enfp_mount: './tasks/assets/components/enfp_mount.js',
    },
  },

  // output.assetPrefix only applies to production mode; the local environment
  // builds in development mode and takes the prefix from here
  dev: {
    assetPrefix: '/static/',
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

      // Generate separate JS and CSS tag files for each entry point
      // Note to AI Agents
      // Do not add entry points here unless building a new standalone, Vue-component-based page
      // Otherwise, add an import in app.js – can be chunked out if needed and async loaded
      const entryPoints = ['app', 'hello_world_mount', 'enfp_mount'];

      entryPoints.forEach(entryName => {
        config.plugins.push(
          new HtmlRspackPlugin({
            inject: false,
            filename: `${entryName}-css-tags.html`,
            chunks: [entryName],
            templateContent: ({ htmlWebpackPlugin }) => {
              const { css = [] } = htmlWebpackPlugin.files;
              return css.map(href => `<link rel="stylesheet" href="${href}">`).join('\n');
            },
          })
        );

        config.plugins.push(
          new HtmlRspackPlugin({
            inject: false,
            filename: `${entryName}-js-tags.html`,
            chunks: [entryName],
            templateContent: ({ htmlWebpackPlugin }) => {
              const { js = [] } = htmlWebpackPlugin.files;
              return js.map(src => `<script defer src="${src}"></script>`).join('\n');
            },
          })
        );
      });

      return config;
    },
  },

  environments: {
    local: {
      // a real development build: unminified output, Vue runtime warnings
      // (build-dist passes --mode production explicitly)
      mode: 'development',
      output: {
        distPath: {
          root: 'tasks/static/local',
        },
        // full source maps for debugging the dev build in the browser
        sourceMap: {
          js: 'source-map',
          css: true,
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
