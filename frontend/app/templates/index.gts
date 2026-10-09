import { pageTitle } from 'ember-page-title';
import ToastRail from 'frontend/components/toast-rail';
import Tour from 'frontend/components/tour';
import Wall from 'frontend/components/wall';

<template>
  {{pageTitle "wall"}}
  <Wall />
  <Tour />
  <ToastRail />
</template>
