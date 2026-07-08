import CopyWebpackPlugin from 'copy-webpack-plugin';
import ESLintPlugin from 'eslint-webpack-plugin';
import ForkTsCheckerWebpackPlugin from 'fork-ts-checker-webpack-plugin';
import path from 'path';
import type { Configuration } from 'webpack';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const ReplaceInFileWebpackPlugin = require('replace-in-file-webpack-plugin');

const SOURCE_DIR = path.resolve(__dirname, '../../src');
const DIST_DIR = path.resolve(__dirname, '../../dist');

const config = async (env: Record<string, unknown>): Promise<Configuration> => {
  const isProduction = env.production === true;

  return {
    mode: isProduction ? 'production' : 'development',
    devtool: isProduction ? 'source-map' : 'eval-source-map',
    entry: {
      module: path.join(SOURCE_DIR, 'module.ts'),
    },
    output: {
      path: DIST_DIR,
      filename: '[name].js',
      library: {
        type: 'amd',
      },
      publicPath: '/',
      uniqueName: '011ybubo-chat-panel',
    },
    externals: [
      'lodash',
      'jquery',
      'moment',
      'slate',
      'emotion',
      '@emotion/react',
      '@emotion/css',
      'prismjs',
      'slate-plain-serializer',
      '@grafana/slate-react',
      'react',
      'react-dom',
      'react-redux',
      'redux',
      'rxjs',
      'd3',
      'angular',
      '@grafana/ui',
      '@grafana/runtime',
      '@grafana/data',
    ],
    resolve: {
      extensions: ['.ts', '.tsx', '.js', '.jsx'],
      modules: [SOURCE_DIR, 'node_modules'],
    },
    module: {
      rules: [
        {
          test: /\.[jt]sx?$/,
          exclude: /node_modules/,
          use: {
            loader: 'swc-loader',
            options: {
              jsc: {
                parser: {
                  syntax: 'typescript',
                  tsx: true,
                  decorators: true,
                },
                target: 'es2021',
                transform: {
                  react: {
                    runtime: 'automatic',
                  },
                },
              },
            },
          },
        },
        {
          test: /\.css$/,
          use: ['style-loader', 'css-loader'],
        },
        {
          test: /\.s[ac]ss$/,
          use: ['style-loader', 'css-loader', 'sass-loader'],
        },
        {
          test: /\.(png|jpe?g|gif|svg)$/,
          type: 'asset/resource',
          generator: {
            publicPath: 'public/plugins/011ybubo-chat-panel/',
            outputPath: 'img/',
            filename: '[name][ext]',
          },
        },
        {
          test: /\.(woff|woff2|eot|ttf|otf)(\?.*)?$/,
          type: 'asset/resource',
          generator: {
            publicPath: 'public/plugins/011ybubo-chat-panel/',
            outputPath: 'fonts/',
            filename: '[name][ext]',
          },
        },
      ],
    },
    plugins: [
      new CopyWebpackPlugin({
        patterns: [
          { from: path.join(SOURCE_DIR, '../plugin.json'), to: '.' },
          { from: path.join(SOURCE_DIR, 'img'), to: 'img', noErrorOnMissing: true },
        ],
      }),
      new ReplaceInFileWebpackPlugin([
        {
          dir: DIST_DIR,
          files: ['plugin.json'],
          rules: [
            {
              search: '%VERSION%',
              replace: require(path.join(SOURCE_DIR, '../package.json')).version,
            },
            {
              search: '%TODAY%',
              replace: new Date().toISOString().substring(0, 10),
            },
          ],
        },
      ]),
      new ForkTsCheckerWebpackPlugin({
        async: Boolean(env.development),
        typescript: {
          configFile: path.join(SOURCE_DIR, '../tsconfig.json'),
        },
      }),
      new ESLintPlugin({
        extensions: ['ts', 'tsx'],
        lintDirtyModulesOnly: Boolean(env.development),
      }),
    ].filter(Boolean),
    optimization: {
      minimize: isProduction,
    },
  };
};

export default config;
