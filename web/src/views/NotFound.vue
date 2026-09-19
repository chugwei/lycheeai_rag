<template>
  <div class="flex h-full items-center justify-center bg-slate-50">
    <div class="text-center">
      <div class="text-6xl font-bold text-slate-300">404</div>
      <h1 class="mt-4 text-xl font-semibold text-slate-700">页面未找到</h1>
      <p class="mt-2 text-sm text-slate-500">你访问的页面不存在，请检查链接是否正确</p>
      <el-button type="primary" class="mt-6" @click="$router.push('/chat')">
        返回问答
      </el-button>
    </div>
  </div>
</template>