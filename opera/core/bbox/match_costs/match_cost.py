# Copyright (c) Hikvision Research Institute. All rights reserved.
import torch
import numpy as np

from .builder import MATCH_COST


@MATCH_COST.register_module()
class KptL1Cost(object):
    """KptL1Cost.

    Args:
        weight (int | float, optional): loss_weight.

    Examples:
        >>> from opera.core.bbox.match_costs.match_cost import KptL1Cost
        >>> import torch
        >>> self = KptL1Cost()
    """

    def __init__(self, weight=1.0):
        self.weight = weight

    def __call__(self, kpt_pred, gt_keypoints, valid_kpt_flag):
        """
        Args:
            kpt_pred (Tensor): Predicted keypoints with normalized coordinates
                (x_{i}, y_{i}), which are all in range [0, 1]. Shape
                [num_query, K, 2].
            gt_keypoints (Tensor): Ground truth keypoints with normalized
                coordinates (x_{i}, y_{i}). Shape [num_gt, K, 2].
            valid_kpt_flag (Tensor): valid flag of ground truth keypoints.
                Shape [num_gt, K].

        Returns:
            torch.Tensor: kpt_cost value with weight.
        """
        kpt_cost = []
        for i in range(len(gt_keypoints)):
            kpt_pred_tmp = kpt_pred.clone()
            valid_flag = valid_kpt_flag[i] > 0
            valid_flag_expand = valid_flag.unsqueeze(0).unsqueeze(
                -1).expand_as(kpt_pred_tmp)
            kpt_pred_tmp[~valid_flag_expand] = 0
            cost = torch.cdist(
                kpt_pred_tmp.reshape(kpt_pred_tmp.shape[0], -1),
                gt_keypoints[i].reshape(-1).unsqueeze(0),
                p=1)
            avg_factor = torch.clamp(valid_flag.float().sum() * 2, 1.0)
            cost = cost / avg_factor
            kpt_cost.append(cost)
        kpt_cost = torch.cat(kpt_cost, dim=1)
        return kpt_cost * self.weight


@MATCH_COST.register_module()
class OksCost(object):
    """OksCost.

    Args:
        weight (int | float, optional): loss_weight.

    Examples:
        >>> from opera.core.bbox.match_costs.match_cost import OksCost
        >>> import torch
        >>> self = OksCost()
    """

    def __init__(self, num_keypoints=17, weight=1.0):
        self.weight = weight
        if num_keypoints == 17:
            self.sigmas = np.array([
                .26,
                .25, .25,
                .35, .35,
                .79, .79,
                .72, .72,
                .62, .62,
                1.07, 1.07,
                .87, .87,
                .89, .89], dtype=np.float32) / 10.0

        elif num_keypoints == 16:
            self.sigmas = np.array([
                .89,  # 0: r_ankle same
                .87,  # 1: r_knee same
                1.07, # 2: r_hip same
                1.07, # 3: l_hip same
                .87,  # 4: l_knee same
                .89,  # 5: l_ankle same
                1.07, # 6: pelvis random
                1.07, # 7: thorax random
                .87,  # 8: upper_neck random
                .89,  # 9: head_top  random
                .62,  # 10: r_wrist same
                .72,  # 11: r_elbow same
                .79,  # 12: r_shoulder same
                .79,  # 13: l_shoulder same
                .72,  # 14: l_elbow same
                .62   # 15: l_wrist same
            ], dtype=np.float32) / 10.0            

        elif num_keypoints == 14:
            self.sigmas = np.array([
                .79, .79,
                .72, .72,
                .62, .62,
                1.07, 1.07,
                .87, .87,
                .89, .89,
                .79, .79], dtype=np.float32) / 10.0
        else:
            raise ValueError(f'Unsupported keypoints number {num_keypoints}')

    def __call__(self, kpt_pred, gt_keypoints, valid_kpt_flag, gt_areas):
        """
        Args:
            kpt_pred (Tensor): Predicted keypoints with unnormalized
                coordinates (x_{i}, y_{i}). Shape [num_query, K, 2].
            gt_keypoints (Tensor): Ground truth keypoints with unnormalized
                coordinates (x_{i}, y_{i}). Shape [num_gt, K, 2].
            valid_kpt_flag (Tensor): valid flag of ground truth keypoints.
                Shape [num_gt, K].
            gt_areas (Tensor): Ground truth mask areas. Shape [num_gt,].

        Returns:
            torch.Tensor: oks_cost value with weight.
        """
        sigmas = torch.from_numpy(self.sigmas).to(kpt_pred.device)
        variances = (sigmas * 2)**2

        oks_cost = []
        assert len(gt_keypoints) == len(gt_areas)
        for i in range(len(gt_keypoints)):
            squared_distance = \
                (kpt_pred[:, :, 0] - gt_keypoints[i, :, 0].unsqueeze(0)) ** 2 + \
                (kpt_pred[:, :, 1] - gt_keypoints[i, :, 1].unsqueeze(0)) ** 2
            vis_flag = (valid_kpt_flag[i] > 0).int()
            vis_ind = vis_flag.nonzero(as_tuple=False)[:, 0]
            num_vis_kpt = vis_ind.shape[0]
            assert num_vis_kpt > 0
            area = gt_areas[i]

            squared_distance0 = squared_distance / (area * variances * 2)
            squared_distance0 = squared_distance0[:, vis_ind]
            squared_distance1 = torch.exp(-squared_distance0).sum(
                dim=1, keepdim=True)
            oks = squared_distance1 / num_vis_kpt
            # The 1 is a constant that doesn't change the matching, so omitted.
            oks_cost.append(-oks)
        oks_cost = torch.cat(oks_cost, dim=1)
        return oks_cost * self.weight
