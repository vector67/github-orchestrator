'use strict';

const weigh = Boolean(process.env.TEST_WEIGH);
const browsers = weigh ? 1 : Number(process.env.TEST_BROWSERS ?? 2);
const partitions = Array.from({ length: browsers }, (_, index) => index + 1);

if (typeof module !== 'undefined') {
  module.exports = {
    test_page:
      browsers > 1
        ? partitions.map(
            (partition) =>
              `tests/index.html?hidepassed&split=${browsers}&partition=${partition}`,
          )
        : `tests/index.html?hidepassed${weigh ? '&weigh' : ''}`,
    cwd: 'dist-tests',
    disable_watching: true,
    parallel: -1,
    launch_in_ci: ['Chrome'],
    launch_in_dev: ['Chrome'],
    browser_start_timeout: 120,
    browser_args: {
      Chrome: {
        ci: [
          // --no-sandbox is needed when running Chrome inside a container
          process.env.CI ? '--no-sandbox' : null,
          '--headless',
          '--disable-dev-shm-usage',
          '--disable-software-rasterizer',
          '--mute-audio',
          '--remote-debugging-port=0',
          '--window-size=1440,900',
        ].filter(Boolean),
      },
    },
  };
}
