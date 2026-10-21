;(function () {
  var config = document.createElement('script')
  config.type = 'application/json'
  config.setAttribute(
    'data-platform-config',
    JSON.stringify({ applicationName: 'GitHub Orchestrator' })
  )
  document.head.appendChild(config)

  var announce = function () {
    var waiting = document.querySelector('.harvest-timer:not([data-listening])')
    var messaging = document.getElementById('harvest-messaging')
    if (waiting && messaging) {
      messaging.dispatchEvent(new CustomEvent('harvest-event:timers:chrome:add'))
    }
  }

  new MutationObserver(announce).observe(document.body, {
    childList: true,
    subtree: true,
  })
})()
