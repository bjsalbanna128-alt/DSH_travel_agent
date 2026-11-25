import { ElMessageBox } from 'element-plus'

export function confirmRecommendationRemoval(title: string) {
  return ElMessageBox.confirm(
    `下架「${title}」后，游客下次加载首页时将看不到这张卡片。`,
    '下架推荐内容', { type: 'warning', confirmButtonText: '确认下架', cancelButtonText: '取消' },
  ).then(() => true, () => false)
}
