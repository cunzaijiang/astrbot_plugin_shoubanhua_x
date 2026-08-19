import json
import asyncio
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from astrbot import logger
from .utils import norm_id


class DataManager:
    def __init__(self, data_dir: Path, config: Any):
        self.data_dir = Path(data_dir)
        self.config = config

        self.user_counts_file = self.data_dir / "user_counts.json"
        self.group_counts_file = self.data_dir / "group_counts.json"
        self.user_checkin_file = self.data_dir / "user_checkin.json"
        self.daily_stats_file = self.data_dir / "daily_stats.json"
        self.preset_images_file = self.data_dir / "preset_images.json"
        self.user_prompts_file = self.data_dir / "user_prompts.json"
        self.preset_ref_images_file = self.data_dir / "preset_ref_images.json"  # 预设参考图索引
        self.history_records_file = self.data_dir / "generation_history.json"  # 生成历史与图片记录
        self.generated_images_dir = self.data_dir / "generated_images"  # 统一生成的图片存储目录
        self.thumbnails_dir = self.data_dir / "thumbnails"  # 高性能轻量缩略图缓存目录
        self.preset_images_dir = self.data_dir / "preset_images"
        self.preset_ref_images_dir = self.data_dir / "preset_ref_images"  # 预设参考图目录
        self.fonts_dir = self.data_dir / "fonts"

        # [Fix] 确保数据目录存在
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self.generated_images_dir.exists():
            self.generated_images_dir.mkdir(parents=True, exist_ok=True)

        if not self.thumbnails_dir.exists():
            self.thumbnails_dir.mkdir(parents=True, exist_ok=True)

        if not self.preset_images_dir.exists():
            self.preset_images_dir.mkdir(parents=True, exist_ok=True)
        
        if not self.preset_ref_images_dir.exists():
            self.preset_ref_images_dir.mkdir(parents=True, exist_ok=True)

        if not self.fonts_dir.exists():
            self.fonts_dir.mkdir(parents=True, exist_ok=True)

        self.user_counts: Dict[str, int] = {}
        self.group_counts: Dict[str, int] = {}
        self.user_checkin_data: Dict[str, str] = {}
        self.daily_stats: Dict[str, Any] = {}
        self.preset_images: Dict[str, str] = {}
        self.user_prompts: Dict[str, str] = {}
        self.preset_ref_images: Dict[str, List[str]] = {}  # 预设参考图: {预设名: [图片文件名列表]}
        self.history_records: List[Dict[str, Any]] = []  # [{id, time, uid, gid, prompt, preset, filename, size, model}]
        self._recorded_image_hashes: set = set()  # 图片内容哈希去重  # [{id, time, uid, gid, prompt, preset, filename, size, model}]
        self.prompt_map: Dict[str, str] = {}

    async def initialize(self):
        await self._load_json(self.user_counts_file, "user_counts")
        await self._load_json(self.group_counts_file, "group_counts")
        await self._load_json(self.user_checkin_file, "user_checkin_data")
        await self._load_json(self.user_prompts_file, "user_prompts")
        await self._load_json(self.preset_ref_images_file, "preset_ref_images")  # 加载预设参考图索引
        await self._load_json(self.history_records_file, "history_records")

        if not self.daily_stats_file.exists():
            self.daily_stats = {"date": "", "users": {}, "groups": {}}
        else:
            await self._load_json(self.daily_stats_file, "daily_stats")

        await self._load_json(self.preset_images_file, "preset_images")
        self.reload_prompts()
        # 初始化时执行一次存储限制检查
        asyncio.create_task(self.check_and_auto_cleanup())

    async def _load_json(self, file_path: Path, attr_name: str):
        if not file_path.exists(): return
        try:
            content = await asyncio.to_thread(file_path.read_text, "utf-8")
            setattr(self, attr_name, json.loads(content))
        except Exception as e:
            logger.error(f"Failed to load {file_path}: {e}")

    async def _save_json(self, file_path: Path, data: Any):
        try:
            content = json.dumps(data, indent=4, ensure_ascii=False)
            await asyncio.to_thread(file_path.write_text, content, "utf-8")
        except Exception as e:
            logger.error(f"Failed to save {file_path}: {e}")

    def reload_prompts(self):
        self.prompt_map.clear()
        # 内置预设
        base_cmd_map = {
            "手办化": "figurine_1", "手办化2": "figurine_2", "手办化3": "figurine_3",
            "手办化4": "figurine_4", "手办化5": "figurine_5", "手办化6": "figurine_6",
            "Q版化": "q_version",
            "痛屋化": "pain_room_1", "痛屋化2": "pain_room_2",
            "痛车化": "pain_car",
            "cos化": "cos", "cos自拍": "cos_selfie",
            "孤独的我": "clown",
            "第三视角": "view_3", "鬼图": "ghost", "第一视角": "view_1"
        }
        for k in base_cmd_map.keys(): self.prompt_map[k] = "[内置预设]"

        # 配置中的 prompts (兼容旧版)
        prompts_cfg = self.config.get("prompts", {})
        if isinstance(prompts_cfg, dict):
            for k, v in prompts_cfg.items():
                if isinstance(v, dict) and "default" in v:
                    self.prompt_map[k] = v["default"]
                elif isinstance(v, str):
                    self.prompt_map[k] = v

        # Prompt List (Config)
        prompt_list = self.config.get("prompt_list", [])
        if isinstance(prompt_list, list):
            for item in prompt_list:
                if ":" in item:
                    k, v = item.split(":", 1)
                    self.prompt_map[k.strip()] = v.strip()
        
        # User Prompts (Persistence) - 优先级最高，覆盖前面的
        for k, v in self.user_prompts.items():
            self.prompt_map[k] = v

    def get_prompt(self, key: str) -> Optional[str]:
        return self.prompt_map.get(key)
        
    async def add_user_prompt(self, key: str, prompt: str):
        """添加或更新用户预设，并持久化保存"""
        self.user_prompts[key] = prompt
        await self._save_json(self.user_prompts_file, self.user_prompts)
        self.reload_prompts()

    async def remove_user_prompt(self, key: str) -> bool:
        """Remove a user-defined prompt preset and persist the change."""
        if key not in self.user_prompts:
            return False
        del self.user_prompts[key]
        await self._save_json(self.user_prompts_file, self.user_prompts)
        self.reload_prompts()
        return True

    async def generate_thumbnail(self, filename: str) -> str:
        """生成并返回经过高压缩的轻量缩略图 (WebP/JPEG, ~20KB) 的 DataURI"""
        if not filename:
            return ""
        
        orig_path = self.generated_images_dir / filename
        if not orig_path.exists():
            return ""

        thumb_filename = f"thumb_{Path(filename).stem}.webp"
        thumb_path = self.thumbnails_dir / thumb_filename

        # 如果已有缓存缩略图文件，直接读取
        if thumb_path.exists():
            try:
                data = await asyncio.to_thread(thumb_path.read_bytes)
                import base64
                return f"data:image/webp;base64,{base64.b64encode(data).decode('utf-8')}"
            except Exception:
                pass

        # 异步生成 320x320 缩略图
        def _make_thumb():
            import io
            import base64
            from PIL import Image
            try:
                with Image.open(orig_path) as im:
                    im = im.convert("RGB")
                    im.thumbnail((320, 320), Image.Resampling.LANCZOS)
                    out_io = io.BytesIO()
                    im.save(out_io, format="WEBP", quality=75, method=4)
                    thumb_bytes = out_io.getvalue()
                    thumb_path.write_bytes(thumb_bytes)
                    return f"data:image/webp;base64,{base64.b64encode(thumb_bytes).decode('utf-8')}"
            except Exception as e:
                logger.error(f"生成缩略图异常 {filename}: {e}")
                return ""

        return await asyncio.to_thread(_make_thumb)

    async def get_raw_image_data_uri(self, filename: str) -> str:
        """获取原图的高清 Base64 DataURI (用于灯箱大图预览)"""
        orig_path = self.generated_images_dir / filename
        if not orig_path.exists():
            return ""
        try:
            import base64
            data = await asyncio.to_thread(orig_path.read_bytes)
            return f"data:image/png;base64,{base64.b64encode(data).decode('utf-8')}"
        except Exception as e:
            logger.error(f"读取原图失败 {filename}: {e}")
            return ""

    def get_all_tracked_user_ids(self) -> List[str]:
        """获取所有已跟踪配额或有调用记录的用户ID列表"""
        ids = set(self.user_counts.keys())
        ids.update(self.user_checkin_data.keys())
        ids.update(self.daily_stats.get("users", {}).keys())
        for r in self.history_records:
            uid = r.get("uid")
            if uid and uid != "WebUI-Admin":
                ids.add(uid)
        return list(ids)

    def get_all_tracked_group_ids(self) -> List[str]:
        """获取所有已跟踪配额或有调用记录的群组ID列表"""
        ids = set(self.group_counts.keys())
        ids.update(self.daily_stats.get("groups", {}).keys())
        for r in self.history_records:
            gid = r.get("gid")
            if gid:
                ids.add(gid)
        return list(ids)

    # --- 积分相关 ---
    def get_user_count(self, uid: str) -> int:
        return self.user_counts.get(norm_id(uid), 0)

    async def decrease_user_count(self, uid: str, amount: int = 1):
        uid = norm_id(uid)
        count = self.get_user_count(uid)
        if amount <= 0 or count <= 0: return
        self.user_counts[uid] = count - min(amount, count)
        await self._save_json(self.user_counts_file, self.user_counts)

    async def add_user_count(self, uid: str, amount: int):
        uid = norm_id(uid)
        self.user_counts[uid] = self.get_user_count(uid) + amount
        await self._save_json(self.user_counts_file, self.user_counts)

    def get_group_count(self, gid: str) -> int:
        return self.group_counts.get(norm_id(gid), 0)

    async def decrease_group_count(self, gid: str, amount: int = 1):
        gid = norm_id(gid)
        count = self.get_group_count(gid)
        if amount <= 0 or count <= 0: return
        self.group_counts[gid] = count - min(amount, count)
        await self._save_json(self.group_counts_file, self.group_counts)

    async def add_group_count(self, gid: str, amount: int):
        gid = norm_id(gid)
        self.group_counts[gid] = self.get_group_count(gid) + amount
        await self._save_json(self.group_counts_file, self.group_counts)

    async def process_checkin(self, uid: str) -> str:
        uid = norm_id(uid)
        today = datetime.now().strftime("%Y-%m-%d")
        if self.user_checkin_data.get(uid) == today:
            return f"已签到。剩余: {self.get_user_count(uid)}"

        reward = int(self.config.get("checkin_fixed_reward", 3))
        if self.config.get("enable_random_checkin", False):
            max_r = int(self.config.get("checkin_random_reward_max", 5))
            reward = random.randint(1, max(1, max_r))

        await self.add_user_count(uid, reward)
        self.user_checkin_data[uid] = today
        await self._save_json(self.user_checkin_file, self.user_checkin_data)
        return f"🎉 签到成功 +{reward}次。"

    async def record_usage(self, uid: str, gid: Optional[str]):
        today = datetime.now().strftime("%Y-%m-%d")
        if self.daily_stats.get("date") != today:
            self.daily_stats = {"date": today, "users": {}, "groups": {}}

        uid = norm_id(uid)
        self.daily_stats["users"][uid] = self.daily_stats["users"].get(uid, 0) + 1
        if gid:
            gid = norm_id(gid)
            self.daily_stats["groups"][gid] = self.daily_stats["groups"].get(gid, 0) + 1
        await self._save_json(self.daily_stats_file, self.daily_stats)

    async def record_generated_image(self, image_bytes: bytes, uid: str, gid: Optional[str],
                                     prompt: str, preset_name: str, model: str = "") -> str:
        """记录并持久化保存生成的图片及元数据"""
        try:
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            record_id = f"gen_{timestamp_str}"
            filename = f"{record_id}.png"
            filepath = self.generated_images_dir / filename
            await asyncio.to_thread(filepath.write_bytes, image_bytes)

            size_bytes = len(image_bytes)
            record = {
                "id": record_id,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "uid": norm_id(uid),
                "gid": norm_id(gid) if gid else "",
                "prompt": prompt,
                "preset": preset_name,
                "model": model,
                "filename": filename,
                "size_bytes": size_bytes,
            }
            self.history_records.insert(0, record)
            # 最多保存 10000 条索引记录
            if len(self.history_records) > 10000:
                self.history_records = self.history_records[:10000]

            await self._save_json(self.history_records_file, self.history_records)
            # 异步检查存储上限触发自动清理
            asyncio.create_task(self.check_and_auto_cleanup())
            return filename
        except Exception as e:
            logger.error(f"记录生成图片失败: {e}")
            return ""

    def get_generated_storage_stats(self) -> Dict[str, Any]:
        """获取已生成图片的总数量、总大小(GB/MB)"""
        total_size_bytes = 0
        file_count = 0
        try:
            for p in self.generated_images_dir.glob("*.png"):
                if p.is_file():
                    total_size_bytes += p.stat().st_size
                    file_count += 1
        except Exception as e:
            logger.error(f"计算图片目录容量失败: {e}")

        size_mb = round(total_size_bytes / (1024 * 1024), 2)
        size_gb = round(total_size_bytes / (1024 * 1024 * 1024), 3)
        return {
            "file_count": file_count,
            "total_size_bytes": total_size_bytes,
            "size_mb": size_mb,
            "size_gb": size_gb,
        }

    async def check_and_auto_cleanup(self) -> int:
        """检查并根据配置的容量上限自动清理最旧的图片 (默认50%)"""
        try:
            max_gb = float(self.config.get("image_storage_max_gb", "5") or "5")
            ratio = float(self.config.get("image_cleanup_ratio", 0.5) or 0.5)
            ratio = max(0.1, min(0.9, ratio))

            stats = self.get_generated_storage_stats()
            if stats["size_gb"] >= max_gb:
                logger.warning(f"生成图片目录容量已达 {stats['size_gb']}GB (上限 {max_gb}GB)，正在自动清理 {int(ratio*100)}% 历史图片...")
                return await self.cleanup_generated_images(ratio=ratio)
        except Exception as e:
            logger.error(f"自动清理历史图片异常: {e}")
        return 0

    async def cleanup_generated_images(self, ratio: float = 0.5) -> int:
        """手动或自动清理指定比例的最旧图片"""
        ratio = max(0.1, min(1.0, float(ratio)))
        files = []
        try:
            for p in self.generated_images_dir.glob("*.png"):
                if p.is_file():
                    files.append((p, p.stat().st_mtime))
        except Exception as e:
            logger.error(f"读取图片列表失败: {e}")
            return 0

        if not files:
            return 0

        # 按修改时间从旧到新排序
        files.sort(key=lambda x: x[1])
        delete_count = int(len(files) * ratio)
        if delete_count < 1 and ratio > 0:
            delete_count = 1

        deleted_filenames = set()
        for i in range(min(delete_count, len(files))):
            target_path, _ = files[i]
            try:
                deleted_filenames.add(target_path.name)
                await asyncio.to_thread(target_path.unlink)
            except Exception as e:
                logger.error(f"删除图片文件 {target_path.name} 失败: {e}")

        # 同步清理历史记录列表
        self.history_records = [r for r in self.history_records if r.get("filename") not in deleted_filenames]
        await self._save_json(self.history_records_file, self.history_records)

        # 同步清理缩略图缓存
        for name in deleted_filenames:
            tb = self.thumbnails_dir / f"thumb_{Path(name).stem}.webp"
            if tb.exists():
                try:
                    await asyncio.to_thread(tb.unlink)
                except Exception:
                    pass

        logger.info(f"已清理 {len(deleted_filenames)} 张历史生成图片 (清理比例: {int(ratio*100)}%)")
        return len(deleted_filenames)
    async def save_preset_image(self, preset_key: str, image_bytes: bytes):
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{preset_key}_{timestamp}.png"
            filepath = self.preset_images_dir / filename
            await asyncio.to_thread(filepath.write_bytes, image_bytes)

            if preset_key in self.preset_images:
                old_f = self.preset_images_dir / self.preset_images[preset_key]
                if old_f.exists(): await asyncio.to_thread(old_f.unlink)

            self.preset_images[preset_key] = filename
            await self._save_json(self.preset_images_file, self.preset_images)
        except Exception as e:
            logger.error(f"Save preset img error: {e}")

    def get_preset_image_path(self, preset_key: str) -> Optional[str]:
        if preset_key not in self.preset_images: return None
        f_path = self.preset_images_dir / self.preset_images[preset_key]
        return str(f_path) if f_path.exists() else None

    # [新增] 统计与清理功能
    async def cleanup_old_presets(self, days: int) -> int:
        count = 0
        now = datetime.now()
        for k, v in list(self.preset_images.items()):
            p = self.preset_images_dir / v
            if p.exists():
                mtime = datetime.fromtimestamp(p.stat().st_mtime)
                if (now - mtime).days > days:
                    await asyncio.to_thread(p.unlink)
                    del self.preset_images[k]
                    count += 1
            else:
                del self.preset_images[k]  # Clean broken link
        if count > 0:
            await self._save_json(self.preset_images_file, self.preset_images)
        return count

    def get_preset_stats(self) -> Tuple[int, float]:
        """返回 (数量, MB大小)"""
        total_size = 0
        count = 0
        for v in self.preset_images.values():
            p = self.preset_images_dir / v
            if p.exists():
                total_size += p.stat().st_size
                count += 1
        return count, total_size / (1024 * 1024)

    # ================= 预设参考图管理 =================

    async def save_preset_ref_image(self, preset_key: str, image_bytes: bytes) -> str:
        """
        保存预设参考图
        
        Args:
            preset_key: 预设名称
            image_bytes: 图片二进制数据
            
        Returns:
            保存的文件名
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            # 清理预设名中的特殊字符
            safe_key = "".join(c if c.isalnum() or c in "_-" else "_" for c in preset_key)
            filename = f"{safe_key}_{timestamp}.png"
            filepath = self.preset_ref_images_dir / filename
            
            await asyncio.to_thread(filepath.write_bytes, image_bytes)
            
            # 更新索引
            if preset_key not in self.preset_ref_images:
                self.preset_ref_images[preset_key] = []
            self.preset_ref_images[preset_key].append(filename)
            
            await self._save_json(self.preset_ref_images_file, self.preset_ref_images)
            logger.info(f"预设参考图已保存: {preset_key} -> {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"保存预设参考图失败: {e}")
            return ""

    async def add_preset_ref_images(self, preset_key: str, image_bytes_list: List[bytes]) -> int:
        """
        批量添加预设参考图
        
        Args:
            preset_key: 预设名称
            image_bytes_list: 图片二进制数据列表
            
        Returns:
            成功保存的图片数量
        """
        count = 0
        for img_bytes in image_bytes_list:
            if await self.save_preset_ref_image(preset_key, img_bytes):
                count += 1
        return count

    def get_preset_ref_image_paths(self, preset_key: str) -> List[str]:
        """
        获取预设的所有参考图路径
        
        Args:
            preset_key: 预设名称
            
        Returns:
            图片文件路径列表
        """
        if preset_key not in self.preset_ref_images:
            return []
        
        paths = []
        for filename in self.preset_ref_images[preset_key]:
            filepath = self.preset_ref_images_dir / filename
            if filepath.exists():
                paths.append(str(filepath))
        return paths

    def has_preset_ref_images(self, preset_key: str) -> bool:
        """检查预设是否有参考图"""
        return preset_key in self.preset_ref_images and len(self.preset_ref_images[preset_key]) > 0

    async def clear_preset_ref_images(self, preset_key: str) -> int:
        """
        清除预设的所有参考图
        
        Args:
            preset_key: 预设名称
            
        Returns:
            删除的图片数量
        """
        if preset_key not in self.preset_ref_images:
            return 0
        
        count = 0
        for filename in self.preset_ref_images[preset_key]:
            filepath = self.preset_ref_images_dir / filename
            if filepath.exists():
                try:
                    await asyncio.to_thread(filepath.unlink)
                    count += 1
                except Exception as e:
                    logger.error(f"删除预设参考图失败: {filepath} - {e}")
        
        del self.preset_ref_images[preset_key]
        await self._save_json(self.preset_ref_images_file, self.preset_ref_images)
        return count

    async def remove_preset_ref_image(self, preset_key: str, index: int) -> bool:
        """
        删除预设的指定参考图
        
        Args:
            preset_key: 预设名称
            index: 图片索引（从0开始）
            
        Returns:
            是否删除成功
        """
        if preset_key not in self.preset_ref_images:
            return False
        
        if index < 0 or index >= len(self.preset_ref_images[preset_key]):
            return False
        
        filename = self.preset_ref_images[preset_key][index]
        filepath = self.preset_ref_images_dir / filename
        
        try:
            if filepath.exists():
                await asyncio.to_thread(filepath.unlink)
            self.preset_ref_images[preset_key].pop(index)
            
            # 如果没有参考图了，删除整个条目
            if not self.preset_ref_images[preset_key]:
                del self.preset_ref_images[preset_key]
            
            await self._save_json(self.preset_ref_images_file, self.preset_ref_images)
            return True
        except Exception as e:
            logger.error(f"删除预设参考图失败: {e}")
            return False

    def get_preset_ref_stats(self) -> Dict[str, Any]:
        """
        获取预设参考图统计信息
        
        Returns:
            {
                "total_presets": 有参考图的预设数量,
                "total_images": 总图片数量,
                "total_size_mb": 总大小(MB),
                "details": {预设名: 图片数量}
            }
        """
        total_images = 0
        total_size = 0
        details = {}
        
        for preset_key, filenames in self.preset_ref_images.items():
            valid_count = 0
            for filename in filenames:
                filepath = self.preset_ref_images_dir / filename
                if filepath.exists():
                    total_size += filepath.stat().st_size
                    valid_count += 1
            total_images += valid_count
            if valid_count > 0:
                details[preset_key] = valid_count
        
        return {
            "total_presets": len(details),
            "total_images": total_images,
            "total_size_mb": total_size / (1024 * 1024),
            "details": details
        }

    async def load_preset_ref_images_bytes(self, preset_key: str) -> List[bytes]:
        """
        加载预设的所有参考图为字节数据
        
        Args:
            preset_key: 预设名称
            
        Returns:
            图片字节数据列表
        """
        paths = self.get_preset_ref_image_paths(preset_key)
        images = []
        
        for path in paths:
            try:
                img_bytes = await asyncio.to_thread(Path(path).read_bytes)
                images.append(img_bytes)
            except Exception as e:
                logger.error(f"加载预设参考图失败: {path} - {e}")
        
        return images
