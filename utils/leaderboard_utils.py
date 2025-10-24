# utils/leaderboard_utils.py

import os
import asyncio
from utils.image_generator import generate_leaderboard_image, generate_family_leaderboard_image

async def regenerate_leaderboard_pages(
    old_mem_psids:    list[str],
    new_mem_psids:    list[str],
    members_map:      dict[str,dict],
    old_fam_names:    list[str],
    new_fam_names:    list[str],
    family_stats_map: dict[str,dict],
    pillow_conf:      dict,
    family_conf:      dict,
    out_dir:          str,
    fallback_logo_url: str | None = None,
):
    """
    Recompute and save only those leaderboard pages whose data changed
    (or whose file is missing) for both members‐points and families‐pts/mem.
    """
    os.makedirs(out_dir, exist_ok=True)

    # ─── Members ─────────────────────────────────────────
    per_page    = 10
    total       = len(new_mem_psids)
    total_pages = (total - 1) // per_page + 1

    for page in range(1, total_pages + 1):
        start       = (page - 1) * per_page
        end         = start + per_page
        slice_psids = new_mem_psids[start:end]
        old_slice   = old_mem_psids[start:end]
        out_path    = os.path.join(out_dir, f"member_points_page_{page}.png")

        # if ranking changed on this page, or file missing, regenerate
        if slice_psids != old_slice or not os.path.isfile(out_path):
            page_members = [members_map[psid] for psid in slice_psids if psid in members_map]

            # run sync image generator in a thread
            await asyncio.to_thread(
                generate_leaderboard_image,
                page_members,
                "points",
                pillow_conf,
                family_conf,
                start,
                total_pages
            )

            # move the “latest” default output into its page slot
            os.replace(
                "assets/outputs/leaderboard.png",
                out_path
            )

    # ─── Families ────────────────────────────────────────
    fam_out = os.path.join(out_dir, "families_pts_mem_page_1.png")
    if new_fam_names != old_fam_names or not os.path.isfile(fam_out):
        ordered_families = [
            family_stats_map[name]
            for name in new_fam_names
            if name in family_stats_map
        ]

        # directly await async generator (returns the path)
        fam_path = await generate_family_leaderboard_image(
            ordered_families,
            pillow_conf,
            family_conf,
            fallback_logo_url=fallback_logo_url
        )

        os.replace(
            fam_path,
            fam_out
        )

