"""
AstrBot 手办化 (FigurinePro) WebUI API 扩展路由
提供 REST API 供 Neo-Brutalism Web 界面进行交互与管理
"""
import os
import json
import time
import base64
import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional
from quart import jsonify, request, send_file
from astrbot import logger

PLUGIN_NAME = "astrbot_plugin_shoubanhua"
WEBUI_LOG_PREFIX = "[Shoubanhua-WebUI]"

class WebApiHandler:
    def __init__(self, plugin: Any):
        self.plugin = plugin
        self.context = plugin.context
        self.data_mgr = plugin.data_mgr
        self.api_mgr = plugin.api_mgr
        self.img_mgr = plugin.img_mgr

    def register_routes(self):
        """注册所有 WebUI API"""
        routes = [
            ("status", self.handle_status, ["GET"], "获取插件运行状态与统计"),
            ("config", self.handle_get_config, ["GET"], "获取当前配置"),
            ("config/save", self.handle_save_config, ["POST"], "保存并更新配置"),
            ("presets", self.handle_get_presets, ["GET"], "获取预设列表与详情"),
            ("presets/save", self.handle_save_preset, ["POST"], "新增或更新预设"),
            ("presets/delete", self.handle_delete_preset, ["POST"], "删除自定义预设"),
            ("keys", self.handle_get_keys, ["GET"], "获取API Keys列表"),
            ("keys/update", self.handle_update_keys, ["POST"], "更新API Keys"),
            ("keys/test", self.handle_test_key, ["POST"], "测试当前API连通性"),
            ("quota/list", self.handle_get_quota_list, ["GET"], "获取用户与群组配额列表"),
            ("quota/set", self.handle_set_quota, ["POST"], "设置用户或群组次数"),
            ("generate", self.handle_generate_image, ["POST"], "Web端直接生成/测试图片"),
            ("gallery", self.handle_get_gallery, ["GET"], "获取已生成历史图片(分页懒加载)"),
            ("gallery/raw", self.handle_get_gallery_raw, ["GET"], "获取高清原图Base64数据"),
            ("gallery/image", self.handle_get_gallery_image, ["GET"], "获取历史生成图片文件"),
            ("gallery/cleanup", self.handle_cleanup_gallery, ["POST"], "手动清理历史生成图片"),
            ("gallery/delete", self.handle_delete_single_image, ["POST"], "单张图片手动删除"),
            ("preset_image", self.handle_get_preset_image, ["GET"], "获取预设预览图"),
            ("persona/config", self.handle_get_persona_config, ["GET"], "获取人设写真配置与参考图"),
            ("persona/save", self.handle_save_persona_config, ["POST"], "保存人设写真配置"),
            ("persona/upload_ref", self.handle_upload_persona_ref, ["POST"], "上传人设参考照片"),
            ("persona/delete_ref", self.handle_delete_persona_ref, ["POST"], "删除人设参考照片"),
        ]

        for route_subpath, handler, methods, desc in routes:
            self._register_api(route_subpath, handler, methods, desc)

    def _register_api(self, route_subpath: str, handler: Any, methods: List[str], desc: str):
        route_path = f"/{PLUGIN_NAME}/{route_subpath.strip('/')}"

        async def wrapped_handler(*args, **kwargs):
            t0 = time.monotonic()
            try:
                res = await handler(*args, **kwargs)
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.info(f"{WEBUI_LOG_PREFIX} {request.method} {route_path} 成功 ({elapsed}ms)")
                return res
            except Exception as e:
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.error(f"{WEBUI_LOG_PREFIX} {request.method} {route_path} 异常 ({elapsed}ms): {e}", exc_info=True)
                return jsonify({"status": "error", "message": f"服务器内部错误: {str(e)}", "data": {}}), 500

        wrapped_handler.__name__ = f"shoubanhua_webui_{handler.__name__}"
        self.context.register_web_api(route_path, wrapped_handler, methods, desc)

    async def handle_status(self):
        """返回插件全局状态数据"""
        today_str = datetime_now = time.strftime("%Y-%m-%d")
        daily_users = len(self.data_mgr.daily_stats.get("users", {}))
        daily_groups = len(self.data_mgr.daily_stats.get("groups", {}))
        
        # 统计总调用
        total_user_calls = sum(self.data_mgr.daily_stats.get("users", {}).values())
        total_group_calls = sum(self.data_mgr.daily_stats.get("groups", {}).values())

        preset_count = len(self.data_mgr.prompt_map)
        builtin_count = sum(1 for v in self.data_mgr.prompt_map.values() if v == "[内置预设]")
        custom_count = preset_count - builtin_count

        current_mode = self.plugin.conf.get("interface_mode", "openai_image")
        current_model = self.plugin.conf.get("model", "nano-banana")
        t2i_model = self.plugin.conf.get("text_to_image_model", "") or current_model
        base_url = self.plugin.conf.get("base_url", "")

        storage_stats = self.data_mgr.get_generated_storage_stats()

        return jsonify({
            "status": "ok",
            "data": {
                "version": "3.0.0",
                "plugin_name": "astrbot_plugin_shoubanhua",
                "display_name": "手办化x",
                "interface_mode": current_mode,
                "current_model": current_model,
                "text_to_image_model": t2i_model,
                "base_url": base_url,
                "today": today_str,
                "storage": storage_stats,
                "stats": {
                    "today_users": daily_users,
                    "today_groups": daily_groups,
                    "today_user_calls": total_user_calls,
                    "today_group_calls": total_group_calls,
                    "total_presets": preset_count,
                    "builtin_presets": builtin_count,
                    "custom_presets": custom_count,
                    "total_users_tracked": len(self.data_mgr.user_counts),
                    "total_groups_tracked": len(self.data_mgr.group_counts),
                }
            }
        })

    async def handle_get_config(self):
        """返回当前插件的完整配置数据"""
        conf_dict = dict(self.plugin.conf) if hasattr(self.plugin.conf, "items") else {}
        # 安全处理 key
        raw_keys = self.plugin.conf.get("api_keys", "")
        keys_list = [k.strip() for k in str(raw_keys).splitlines() if k.strip()] if isinstance(raw_keys, str) else list(raw_keys)

        return jsonify({
            "status": "ok",
            "data": {
                "config": conf_dict,
                "api_keys_count": len(keys_list),
                "model_list": self.plugin.conf.get("model_list", []),
            }
        })

    async def handle_save_config(self):
        """保存前端提交的配置"""
        data = await request.get_json(silent=True) or {}
        config_patch = data.get("config", {})
        if not isinstance(config_patch, dict):
            return jsonify({"status": "error", "message": "配置格式错误"}), 400

        changed_keys = []
        for k, v in config_patch.items():
            # 兼容 AstrBot schema 格式要求
            if k == "image_storage_max_gb":
                v = str(int(float(v))) if isinstance(v, (int, float, str)) and str(v).strip() else "5"
            self.plugin.conf[k] = v
            changed_keys.append(k)

        # 保存配置（调用 AstrBot 原生 save_config 与双向持久化）
        self.plugin._save_config(changed_keys=changed_keys)
        
        # 重新热载 api_mgr / img_mgr / data_mgr
        if hasattr(self.plugin, "api_mgr"):
            self.plugin.api_mgr = self.plugin.api_mgr.__class__(self.plugin.conf)
        if hasattr(self.plugin, "img_mgr"):
            self.plugin.img_mgr = self.plugin.img_mgr.__class__(self.plugin.conf)
        if hasattr(self.data_mgr, "reload_prompts"):
            self.data_mgr.reload_prompts()

        return jsonify({"status": "ok", "message": f"成功保存 {len(changed_keys)} 项配置", "data": {"saved_keys": changed_keys}})

    async def handle_get_presets(self):
        """获取所有预设（内置与自定义）及相关提示词"""
        presets = []
        user_prompts = getattr(self.data_mgr, "user_prompts", {})
        preset_ref_images = getattr(self.data_mgr, "preset_ref_images", {})

        hardcoded_builtin = {
            "手办化", "手办化2", "手办化3", "手办化4", "手办化5", "手办化6",
            "Q版化", "痛屋化", "痛屋化2", "痛车化", "cos化", "cos自拍",
            "孤独的我", "第三视角", "鬼图", "第一视角"
        }

        for name, prompt_text in self.data_mgr.prompt_map.items():
            is_builtin = name in hardcoded_builtin
            real_prompt = prompt_text
            if prompt_text == "[内置预设]":
                # 获取内置对应的提示词
                real_prompt = self.plugin._get_builtin_preset_prompt(name) if hasattr(self.plugin, "_get_builtin_preset_prompt") else "【内置系统级预设提示词】"

            has_image = name in self.data_mgr.preset_images or (self.data_mgr.preset_images_dir / f"{name}.png").exists()
            ref_imgs = preset_ref_images.get(name, [])

            presets.append({
                "name": name,
                "is_builtin": is_builtin,
                "prompt": real_prompt if isinstance(real_prompt, str) else str(real_prompt),
                "has_preview": has_image,
                "ref_images_count": len(ref_imgs),
                "ref_images": ref_imgs,
            })

        presets.sort(key=lambda x: (not x["is_builtin"], x["name"]))
        return jsonify({"status": "ok", "data": {"presets": presets}})

    async def handle_save_preset(self):
        """新增或更新自定义预设"""
        data = await request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        prompt = str(data.get("prompt", "")).strip()

        if not name or not prompt:
            return jsonify({"status": "error", "message": "预设名与提示词不能为空"}), 400

        # 保存到 user_prompts
        if not hasattr(self.data_mgr, "user_prompts"):
            self.data_mgr.user_prompts = {}
        self.data_mgr.user_prompts[name] = prompt
        await self.data_mgr._save_json(self.data_mgr.user_prompts_file, self.data_mgr.user_prompts)
        self.data_mgr.reload_prompts()

        return jsonify({"status": "ok", "message": f"预设 [{name}] 保存成功"})

    async def handle_delete_preset(self):
        """删除自定义预设（包括 user_prompts 与 prompt_list 配置）"""
        data = await request.get_json(silent=True) or {}
        name = str(data.get("name", "")).strip()
        if not name:
            return jsonify({"status": "error", "message": "未指定预设名"}), 400

        # 系统硬编码核心内置预设（不可删除）
        hardcoded_builtin = {
            "手办化", "手办化2", "手办化3", "手办化4", "手办化5", "手办化6",
            "Q版化", "痛屋化", "痛屋化2", "痛车化", "cos化", "cos自拍",
            "孤独的我", "第三视角", "鬼图", "第一视角"
        }
        if name in hardcoded_builtin:
            return jsonify({"status": "error", "message": f"预设 [{name}] 为系统核心内置预设，无法删除"}), 400

        deleted = False

        # 1. 尝试从 user_prompts 中删除
        if hasattr(self.data_mgr, "user_prompts") and name in self.data_mgr.user_prompts:
            del self.data_mgr.user_prompts[name]
            await self.data_mgr._save_json(self.data_mgr.user_prompts_file, self.data_mgr.user_prompts)
            deleted = True

        # 2. 尝试从 config.prompt_list 中删除
        prompt_list = self.plugin.conf.get("prompt_list", [])
        if isinstance(prompt_list, list):
            new_list = [item for item in prompt_list if not (item.startswith(f"{name}:") or item.strip() == name)]
            if len(new_list) != len(prompt_list):
                self.plugin.conf["prompt_list"] = new_list
                self.plugin._save_config(changed_keys=["prompt_list"])
                deleted = True

        if not deleted:
            return jsonify({"status": "error", "message": f"预设 [{name}] 不存在或无法删除"}), 400

        self.data_mgr.reload_prompts()

        # 清理可能存在的参考图与预览图
        try:
            if hasattr(self.data_mgr, "delete_preset_ref_images"):
                await self.data_mgr.delete_preset_ref_images(name)
        except Exception:
            pass

        return jsonify({"status": "ok", "message": f"预设 [{name}] 已成功删除！"})

    async def handle_get_keys(self):
        """获取当前配置的 API Key 列表"""
        raw_keys = self.plugin.conf.get("api_keys", "")
        keys_list = [k.strip() for k in str(raw_keys).splitlines() if k.strip()] if isinstance(raw_keys, str) else list(raw_keys)
        
        # 掩码脱敏
        masked_keys = []
        for idx, k in enumerate(keys_list, 1):
            if len(k) > 10:
                masked = f"{k[:4]}...{k[-4:]}"
            else:
                masked = "***"
            masked_keys.append({"index": idx, "key": k, "masked": masked})

        return jsonify({
            "status": "ok",
            "data": {
                "keys": masked_keys,
                "total": len(masked_keys),
                "interface_mode": self.plugin.conf.get("interface_mode", "openai_image"),
                "base_url": self.plugin.conf.get("base_url", "")
            }
        })

    async def handle_update_keys(self):
        """更新 API Key 池"""
        data = await request.get_json(silent=True) or {}
        keys = data.get("keys", [])
        if isinstance(keys, list):
            cleaned = "\n".join([str(k).strip() for k in keys if str(k).strip()])
        elif isinstance(keys, str):
            cleaned = keys.strip()
        else:
            return jsonify({"status": "error", "message": "Key数据格式不正确"}), 400

        self.plugin.conf["api_keys"] = cleaned
        self.plugin._save_config(changed_keys=["api_keys"])
        self.plugin.api_mgr = self.plugin.api_mgr.__class__(self.plugin.conf)

        return jsonify({"status": "ok", "message": "API Key 池已更新"})

    async def handle_test_key(self):
        """测试生图接口连通性（向接口发送真实的测试提示词调用生图模型）"""
        data = await request.get_json(silent=True) or {}
        test_prompt = str(data.get("prompt", "a tiny cute plastic figure on a wooden desk, masterwork, masterpiece")).strip()
        custom_model = str(data.get("model", "")).strip()

        current_model = custom_model or self.plugin._get_text_to_image_model() or self.plugin._get_current_model()
        mode = self.plugin.conf.get("interface_mode", "openai_image")
        base_url = self.plugin.conf.get("base_url", "")
        
        # 验证 key 是否存在
        raw_keys = self.plugin.conf.get("api_keys", "")
        keys_list = [k.strip() for k in str(raw_keys).splitlines() if k.strip()] if isinstance(raw_keys, str) else list(raw_keys)
        if not keys_list and mode != "gemini_official" and not self.plugin.conf.get("backup_providers"):
            return jsonify({"status": "error", "message": "未配置任何 API Key"}), 400

        t0 = time.monotonic()
        try:
            # 真实调用 call_api 生成一张测试图片
            res = await self.api_mgr.call_api(
                [], test_prompt, current_model, False, self.img_mgr.proxy,
                use_text_to_image_api=True
            )
            elapsed = round(time.monotonic() - t0, 2)
            if isinstance(res, bytes) and res:
                img_b64 = f"data:image/png;base64,{base64.b64encode(res).decode('utf-8')}"
                return jsonify({
                    "status": "ok",
                    "message": f"🎉 绘图模型调用测试成功！(耗时 {elapsed}s)",
                    "data": {
                        "image": img_b64,
                        "model": current_model,
                        "elapsed": elapsed,
                        "prompt": test_prompt,
                        "metrics": self.api_mgr.get_last_metrics()
                    }
                })
            else:
                return jsonify({
                    "status": "error",
                    "message": f"绘图测试失败: {res}",
                    "data": {"elapsed": elapsed, "model": current_model}
                }), 400
        except Exception as e:
            elapsed = round(time.monotonic() - t0, 2)
            return jsonify({
                "status": "error",
                "message": f"测试调用异常: {str(e)}",
                "data": {"elapsed": elapsed}
            }), 500

    async def handle_get_quota_list(self):
        """获取所有记录的用户和群组配额与统计"""
        users = []
        tracked_user_ids = self.data_mgr.get_all_tracked_user_ids()
        for uid in tracked_user_ids:
            count = self.data_mgr.get_user_count(uid)
            checkin = self.data_mgr.user_checkin_data.get(uid, "未签到")
            today_calls = self.data_mgr.daily_stats.get("users", {}).get(uid, 0)
            users.append({
                "id": uid,
                "quota": count,
                "last_checkin": checkin,
                "today_calls": today_calls
            })

        groups = []
        tracked_group_ids = self.data_mgr.get_all_tracked_group_ids()
        for gid in tracked_group_ids:
            count = self.data_mgr.get_group_count(gid)
            today_calls = self.data_mgr.daily_stats.get("groups", {}).get(gid, 0)
            groups.append({
                "id": gid,
                "quota": count,
                "today_calls": today_calls
            })

        users.sort(key=lambda x: (x["today_calls"], x["quota"]), reverse=True)
        groups.sort(key=lambda x: (x["today_calls"], x["quota"]), reverse=True)

        return jsonify({
            "status": "ok",
            "data": {
                "users": users[:100],  # 限制前100条
                "groups": groups[:100],
                "user_limit_enabled": self.plugin.conf.get("enable_user_limit", True),
                "group_limit_enabled": self.plugin.conf.get("enable_group_limit", False),
                "checkin_enabled": self.plugin.conf.get("enable_checkin", False)
            }
        })

    async def handle_set_quota(self):
        """设置用户或群组次数"""
        data = await request.get_json(silent=True) or {}
        target_type = data.get("type", "user")  # user 或 group
        target_id = str(data.get("id", "")).strip()
        delta_or_set = data.get("value", 0)
        mode = data.get("mode", "add")  # "add" 或 "set"

        if not target_id:
            return jsonify({"status": "error", "message": "ID 不能为空"}), 400

        try:
            val = int(delta_or_set)
        except ValueError:
            return jsonify({"status": "error", "message": "次数数值无效"}), 400

        if target_type == "user":
            if mode == "set":
                self.data_mgr.user_counts[target_id] = max(0, val)
            else:
                current = self.data_mgr.user_counts.get(target_id, 0)
                self.data_mgr.user_counts[target_id] = max(0, current + val)
            await self.data_mgr._save_json(self.data_mgr.user_counts_file, self.data_mgr.user_counts)
            new_val = self.data_mgr.user_counts[target_id]
        else:
            if mode == "set":
                self.data_mgr.group_counts[target_id] = max(0, val)
            else:
                current = self.data_mgr.group_counts.get(target_id, 0)
                self.data_mgr.group_counts[target_id] = max(0, current + val)
            await self.data_mgr._save_json(self.data_mgr.group_counts_file, self.data_mgr.group_counts)
            new_val = self.data_mgr.group_counts[target_id]

        return jsonify({
            "status": "ok",
            "message": f"已将 {target_type} [{target_id}] 的剩余次数更新为 {new_val}",
            "data": {"id": target_id, "quota": new_val}
        })

    async def handle_generate_image(self):
        """WebUI 在线文生图 / 图生图调试接口"""
        data = await request.get_json(silent=True) or {}
        prompt = str(data.get("prompt", "")).strip()
        preset = str(data.get("preset", "")).strip()
        custom_model = str(data.get("model", "")).strip()
        input_image_b64 = data.get("image_base64", "")

        if not prompt and not preset:
            return jsonify({"status": "error", "message": "提示词和预设不能同时为空"}), 400

        # 处理提示词与预设
        full_text = f"{preset} {prompt}".strip() if preset else prompt
        final_prompt, preset_name, extra_rules = self.plugin._process_prompt_and_preset(full_text)

        images = []
        if input_image_b64:
            try:
                if "," in input_image_b64:
                    input_image_b64 = input_image_b64.split(",", 1)[1]
                images.append(base64.b64decode(input_image_b64))
            except Exception as e:
                return jsonify({"status": "error", "message": f"解码输入图片失败: {e}"}), 400
        elif preset_name != "自定义" and self.plugin.conf.get("enable_preset_ref_images", True):
            ref_images = await self.plugin._load_preset_ref_images(preset_name)
            if ref_images:
                images = ref_images

        model = custom_model or (self.plugin._get_text_to_image_model() if not images else self.plugin._get_current_model())
        is_t2i = (len(images) == 0)

        t0 = time.monotonic()
        try:
            res = await self.api_mgr.call_api(
                images, final_prompt, model, False, self.img_mgr.proxy,
                use_text_to_image_api=is_t2i
            )
            elapsed = round(time.monotonic() - t0, 2)
            if isinstance(res, bytes):
                # 记录保存到历史
                await self.data_mgr.record_generated_image(
                    image_bytes=res,
                    uid="WebUI-Admin",
                    gid="",
                    prompt=final_prompt,
                    preset_name=preset_name,
                    model=model
                )
                img_b64 = f"data:image/png;base64,{base64.b64encode(res).decode('utf-8')}"
                return jsonify({
                    "status": "ok",
                    "data": {
                        "image": img_b64,
                        "model": model,
                        "elapsed": elapsed,
                        "prompt": final_prompt,
                        "preset": preset_name
                    }
                })
            else:
                return jsonify({"status": "error", "message": str(res)}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": f"生图失败: {e}"}), 500

    async def handle_get_gallery(self):
        """获取已生成历史图片列表（支持 30 张一页分页懒加载）"""
        page = max(1, int(request.args.get("page", 1)))
        page_size = max(1, min(100, int(request.args.get("page_size", 30))))

        all_records = self.data_mgr.history_records
        total = len(all_records)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paged_records = all_records[start_idx:end_idx]

        items = []
        # 并发生成/获取这 30 张图片的缩略图
        thumb_tasks = [self.data_mgr.generate_thumbnail(r.get("filename", "")) for r in paged_records]
        thumbnails = await asyncio.gather(*thumb_tasks, return_exceptions=True)

        for idx, r in enumerate(paged_records):
            filename = r.get("filename", "")
            thumb_b64 = thumbnails[idx] if idx < len(thumbnails) and isinstance(thumbnails[idx], str) else ""

            items.append({
                "id": r.get("id"),
                "time": r.get("time"),
                "uid": r.get("uid"),
                "gid": r.get("gid"),
                "prompt": r.get("prompt"),
                "preset": r.get("preset"),
                "model": r.get("model"),
                "filename": filename,
                "size_kb": round(r.get("size_bytes", 0) / 1024, 1),
                "url": thumb_b64,  # 超轻量 WebP 缩略图 (~20KB)
            })

        storage_info = self.data_mgr.get_generated_storage_stats()

        return jsonify({
            "status": "ok",
            "data": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
                "items": items,
                "storage": storage_info,
                "max_gb": float(self.plugin.conf.get("image_storage_max_gb", 5.0) or 5.0),
                "cleanup_ratio": float(self.plugin.conf.get("image_cleanup_ratio", 0.5) or 0.5)
            }
        })

    async def handle_get_gallery_raw(self):
        """按需获取单张图片的高清原图 DataURI (点击预览大图时才调用)"""
        filename = str(request.args.get("filename", "")).strip()
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"status": "error", "message": "无效的文件名"}), 400

        data_uri = await self.data_mgr.get_raw_image_data_uri(filename)
        if not data_uri:
            return jsonify({"status": "error", "message": "图片不存在或已清理"}), 404

        return jsonify({
            "status": "ok",
            "data": {
                "filename": filename,
                "data_uri": data_uri
            }
        })

    async def handle_get_gallery_image(self):
        """获取已生成图片文件"""
        filename = request.args.get("filename", "")
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"status": "error", "message": "无效的文件名"}), 400

        img_path = self.data_mgr.generated_images_dir / filename
        if not img_path.exists():
            return jsonify({"status": "error", "message": "图片文件不存在或已被清理"}), 404

        return await send_file(img_path, mimetype="image/png")

    async def handle_cleanup_gallery(self):
        """手动立即清理历史图片"""
        data = await request.get_json(silent=True) or {}
        ratio = float(data.get("ratio", 0.5))
        deleted_count = await self.data_mgr.cleanup_generated_images(ratio=ratio)
        storage_info = self.data_mgr.get_generated_storage_stats()
        return jsonify({
            "status": "ok",
            "message": f"成功清理 {deleted_count} 张历史图片，当前剩余占用: {storage_info['size_mb']} MB",
            "data": {
                "deleted_count": deleted_count,
                "storage": storage_info
            }
        })

    async def handle_delete_single_image(self):
        """删除指定的单张历史生成图片"""
        data = await request.get_json(silent=True) or {}
        filename = str(data.get("filename", "")).strip()
        if not filename or ".." in filename or "/" in filename or "\\" in filename:
            return jsonify({"status": "error", "message": "无效的文件名"}), 400

        img_path = self.data_mgr.generated_images_dir / filename
        if img_path.exists():
            try:
                await asyncio.to_thread(img_path.unlink)
            except Exception as e:
                logger.error(f"删除单张图片文件失败: {e}")

        # 从记录中移除
        self.data_mgr.history_records = [r for r in self.data_mgr.history_records if r.get("filename") != filename]
        await self.data_mgr._save_json(self.data_mgr.history_records_file, self.data_mgr.history_records)
        storage_info = self.data_mgr.get_generated_storage_stats()
        return jsonify({
            "status": "ok",
            "message": "图片已成功删除",
            "data": {"storage": storage_info}
        })

    async def handle_get_preset_image(self):
        """获取内置或自定义预设的示意图片"""
        name = str(request.args.get("name", "")).strip()
        if not name:
            return jsonify({"status": "error", "message": "缺少预设名称"}), 400

        # 检查自定义图片
        custom_img = self.data_mgr.preset_images_dir / f"{name}.png"
        if custom_img.exists():
            return await send_file(custom_img, mimetype="image/png")

        # 检查内置 demo 图片
        demo_map = {
            "手办化": "figurine_demo.png",
            "cos化": "cos_demo.png",
            "第一视角": "pov1_demo.png",
            "第三视角": "pov3_demo.png",
        }
        if name in demo_map:
            demo_path = Path(self.plugin.context.get_data_dir()).parent / "plugins" / PLUGIN_NAME / "images" / demo_map[name]
            if demo_path.exists():
                return await send_file(demo_path, mimetype="image/png")

        return jsonify({"status": "error", "message": "暂无示意图"}), 404

    async def handle_get_persona_config(self):
        """获取人设写真配置与参考图列表 (Base64)"""
        persona_name = self.plugin.conf.get("persona_name", "诺亚")
        persona_desc = self.plugin.conf.get("persona_description", "")
        photo_style = self.plugin.conf.get("persona_photo_style", "日常生活风格，自然光线，真实感")
        default_prompt = self.plugin.conf.get("persona_default_prompt", "一张日常生活照片，自然的姿态和表情")
        trigger_keywords = self.plugin.conf.get("persona_trigger_keywords", ["拍照", "自拍", "看看你"])
        scene_prompts = self.plugin.conf.get("persona_scene_prompts", [
            "咖啡店:在咖啡店里悠闲地喝咖啡",
            "家里:在房间里的日常生活场景",
            "公园:在公园里散步或休息",
            "学校:在校园里的日常"
        ])
        enable_persona = self.plugin.conf.get("enable_persona_mode", True)

        # 读取参考图列表
        ref_images = []
        if self.data_mgr.has_preset_ref_images("_persona_"):
            paths = self.data_mgr.get_preset_ref_image_paths("_persona_")
            for idx, p in enumerate(paths):
                try:
                    fpath = Path(p)
                    if fpath.exists():
                        b_data = fpath.read_bytes()
                        b64 = base64.b64encode(b_data).decode("utf-8")
                        ref_images.append({
                            "index": idx,
                            "filename": fpath.name,
                            "url": f"data:image/png;base64,{b64}",
                            "size_kb": round(len(b_data) / 1024, 1)
                        })
                except Exception as e:
                    logger.error(f"读取人设参考图失败 {p}: {e}")

        return jsonify({
            "status": "ok",
            "data": {
                "enable_persona_mode": bool(enable_persona),
                "persona_name": persona_name,
                "persona_description": persona_desc,
                "persona_photo_style": photo_style,
                "persona_default_prompt": default_prompt,
                "persona_trigger_keywords": trigger_keywords,
                "persona_scene_prompts": scene_prompts,
                "ref_images": ref_images
            }
        })

    async def handle_save_persona_config(self):
        """保存人设写真各项配置"""
        data = await request.get_json(silent=True) or {}
        fields = [
            "enable_persona_mode", "persona_name", "persona_description",
            "persona_photo_style", "persona_default_prompt",
            "persona_trigger_keywords", "persona_scene_prompts"
        ]
        changed_keys = []
        for field in fields:
            if field in data:
                self.plugin.conf[field] = data[field]
                changed_keys.append(field)

        self.plugin._save_config(changed_keys=changed_keys)
        return jsonify({"status": "ok", "message": "人设配置已保存并热生效！"})

    async def handle_upload_persona_ref(self):
        """上传单张或多张人设参考图 (Base64)"""
        data = await request.get_json(silent=True) or {}
        image_base64 = data.get("image_base64", "")
        if not image_base64:
            return jsonify({"status": "error", "message": "未提供图片数据"}), 400

        try:
            # 清理 data URL 前缀
            if "," in image_base64:
                image_base64 = image_base64.split(",", 1)[1]
            img_bytes = base64.b64decode(image_base64)
            saved_name = await self.data_mgr.save_preset_ref_image("_persona_", img_bytes)
            if not saved_name:
                return jsonify({"status": "error", "message": "保存人设参考图失败"}), 500

            return jsonify({"status": "ok", "message": "人设参考图上传成功！", "data": {"filename": saved_name}})
        except Exception as e:
            logger.error(f"处理人设图片上传异常: {e}")
            return jsonify({"status": "error", "message": f"上传异常: {e}"}), 500

    async def handle_delete_persona_ref(self):
        """删除指定索引或文件名的人设参考图"""
        data = await request.get_json(silent=True) or {}
        index = data.get("index")
        if index is None:
            return jsonify({"status": "error", "message": "缺少图片索引"}), 400

        success = await self.data_mgr.remove_preset_ref_image("_persona_", int(index))
        if not success:
            return jsonify({"status": "error", "message": "删除失败，图片可能不存在"}), 400

        return jsonify({"status": "ok", "message": "人设参考图已删除！"})
