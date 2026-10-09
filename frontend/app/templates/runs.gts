import { pageTitle } from 'ember-page-title';
import RunsPage from 'frontend/components/runs-page';
import ToastRail from 'frontend/components/toast-rail';

<template>
  {{pageTitle "runs"}}
  <RunsPage />
  <ToastRail />
</template>
