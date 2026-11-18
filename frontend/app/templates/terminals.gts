import { pageTitle } from 'ember-page-title';
import TerminalsPage from 'frontend/components/terminals-page';
import ToastRail from 'frontend/components/toast-rail';

<template>
  {{pageTitle "terminals"}}
  <TerminalsPage />
  <ToastRail />
</template>
