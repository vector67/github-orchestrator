import Waiting from 'frontend/components/waiting';

<template>
  <div class="page-loading">
    <p class="work-placeholder" id="loading" data-test-loading="board">
      Loading the board…
    </p>
    <Waiting />
  </div>
</template>
