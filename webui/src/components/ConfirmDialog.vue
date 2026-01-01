<script setup lang="ts">
import { confirmState, closeConfirm } from "../confirm";
import Modal from "./Modal.vue";
import Button from "./Button.vue";
</script>

<template>
  <Modal :open="confirmState.isOpen" :title="confirmState.title" @close="closeConfirm(false)">
    <div class="space-y-4">
      <p class="text-sm text-slate-600 dark:text-slate-300">{{ confirmState.message }}</p>
      <div class="flex justify-end gap-3">
        <Button @click="closeConfirm(false)">取消</Button>
        <Button variant="danger" @click="closeConfirm(true)">确定</Button>
      </div>
    </div>
  </Modal>
</template>
