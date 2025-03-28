""" EfficientDet Focal, Huber/Smooth L1 loss fns w/ jit support

Based on loss fn in Google's automl EfficientDet repository (Apache 2.0 license).
https://github.com/google/automl/tree/master/efficientdet

Copyright 2020 Ross Wightman
"""
import torch
import torch.nn as nn
import torch.nn.functional as F

from typing import Optional, List, Tuple

from effdet.anchors import decode_box_outputs


def focal_loss_legacy(logits, targets, alpha: float, gamma: float, normalizer):
    """Compute the focal loss between `logits` and the golden `target` values.

    'Legacy focal loss matches the loss used in the official Tensorflow impl for initial
    model releases and some time after that. It eventually transitioned to the 'New' loss
    defined below.

    Focal loss = -(1-pt)^gamma * log(pt)
    where pt is the probability of being classified to the true class.

    Args:
        logits: A float32 tensor of size [batch, height_in, width_in, num_predictions].

        targets: A float32 tensor of size [batch, height_in, width_in, num_predictions].

        alpha: A float32 scalar multiplying alpha to the loss from positive examples
            and (1-alpha) to the loss from negative examples.

        gamma: A float32 scalar modulating loss from hard and easy examples.

         normalizer: A float32 scalar normalizes the total loss from all examples.

    Returns:
        loss: A float32 scalar representing normalized total loss.
    """
    positive_label_mask = targets == 1.0
    cross_entropy = F.binary_cross_entropy_with_logits(logits, targets.to(logits.dtype), reduction='none')
    neg_logits = -1.0 * logits
    modulator = torch.exp(gamma * targets * neg_logits - gamma * torch.log1p(torch.exp(neg_logits)))

    loss = modulator * cross_entropy
    weighted_loss = torch.where(positive_label_mask, alpha * loss, (1.0 - alpha) * loss)
    return weighted_loss / normalizer


def new_focal_loss(logits, targets, alpha: float, gamma: float, normalizer, label_smoothing: float = 0.01):
    """Compute the focal loss between `logits` and the golden `target` values.

    'New' is not the best descriptor, but this focal loss impl matches recent versions of
    the official Tensorflow impl of EfficientDet. It has support for label smoothing, however
    it is a bit slower, doesn't jit optimize well, and uses more memory.

    Focal loss = -(1-pt)^gamma * log(pt)
    where pt is the probability of being classified to the true class.
    Args:
        logits: A float32 tensor of size [batch, height_in, width_in, num_predictions].
        targets: A float32 tensor of size [batch, height_in, width_in, num_predictions].
        alpha: A float32 scalar multiplying alpha to the loss from positive examples
            and (1-alpha) to the loss from negative examples.
        gamma: A float32 scalar modulating loss from hard and easy examples.
        normalizer: Divide loss by this value.
        label_smoothing: Float in [0, 1]. If > `0` then smooth the labels.
    Returns:
        loss: A float32 scalar representing normalized total loss.
    """
    # compute focal loss multipliers before label smoothing, such that it will not blow up the loss.
    pred_prob = logits.sigmoid()
    targets = targets.to(logits.dtype)
    onem_targets = 1. - targets
    p_t = (targets * pred_prob) + (onem_targets * (1. - pred_prob))
    alpha_factor = targets * alpha + onem_targets * (1. - alpha)
    modulating_factor = (1. - p_t) ** gamma

    # apply label smoothing for cross_entropy for each entry.
    if label_smoothing > 0.:
        targets = targets * (1. - label_smoothing) + .5 * label_smoothing
    ce = F.binary_cross_entropy_with_logits(logits, targets, reduction='none')

    # compute the final loss and return
    return (1 / normalizer) * alpha_factor * modulating_factor * ce


def huber_loss(
        input, target, delta: float = 1., weights: Optional[torch.Tensor] = None, size_average: bool = True):
    """
    """
    err = input - target
    abs_err = err.abs()
    quadratic = torch.clamp(abs_err, max=delta)
    linear = abs_err - quadratic
    loss = 0.5 * quadratic.pow(2) + delta * linear
    if weights is not None:
        loss = loss.mul(weights)
    if size_average:
        return loss.mean()
    else:
        return loss.sum()


def smooth_l1_loss(
        input, target, beta: float = 1. / 9, weights: Optional[torch.Tensor] = None, size_average: bool = True):
    """
    very similar to the smooth_l1_loss from pytorch, but with the extra beta parameter
    """
    if beta < 1e-5:
        # if beta == 0, then torch.where will result in nan gradients when
        # the chain rule is applied due to pytorch implementation details
        # (the False branch "0.5 * n ** 2 / 0" has an incoming gradient of
        # zeros, rather than "no gradient"). To avoid this issue, we define
        # small values of beta to be exactly l1 loss.
        loss = torch.abs(input - target)
    else:
        err = torch.abs(input - target)
        loss = torch.where(err < beta, 0.5 * err.pow(2) / beta, err - 0.5 * beta)
    if weights is not None:
        loss *= weights
    if size_average:
        return loss.mean()
    else:
        return loss.sum()


def _iou(decoded_output, decoded_target):
    eps = 1e-7

    # area of gt
    Ag = (decoded_target[:, 3] - decoded_target[:, 1]) * (decoded_target[:, 2] - decoded_target[:, 0])

    # area of pred
    Ap = (decoded_output[:, 3] - decoded_output[:, 1]) * (decoded_output[:, 2] - decoded_output[:, 0])

    # intersection
    yI_1 = torch.max(decoded_target[:, 0], decoded_output[:, 0])
    xI_1 = torch.max(decoded_target[:, 1], decoded_output[:, 1])
    yI_2 = torch.min(decoded_target[:, 2], decoded_output[:, 2])
    xI_2 = torch.min(decoded_target[:, 3], decoded_output[:, 3])
    I = (xI_2 - xI_1) * (yI_2 - yI_1)
    I_cond = torch.logical_and(xI_2 > xI_1, yI_2 > yI_1)
    I = torch.where(I_cond, I, 0.0)

    # union
    U = Ap + Ag - I

    return I/(U + eps), U


def _box_loss(outputs, targets, anchors, num_positives, loss_type: str):
    """Computes box regression loss."""
    # delta is typically around the mean value of regression target.
    # for instances, the regression targets of 512x512 input with 6 anchors on
    # P3-P7 pyramid is about [0.1, 0.1, 0.2, 0.2].

    eps = 1e-7
    loss = []
    anchors = anchors.to(targets.device)
    for output, target in zip(outputs, targets): # batch-level
        mask = torch.all(target != 0.0, dim=1)
        rel_anchors = anchors[mask, :].reshape([-1, 4])

        target = target[mask, :].reshape([-1, 4])
        decoded_target = decode_box_outputs(target, rel_anchors) # yxyx

        output = output[mask, :].reshape([-1, 4])
        decoded_output = decode_box_outputs(output, rel_anchors) # yxyx

        iou, U = _iou(decoded_output, decoded_target)

        penalty = 0.
        if loss_type == 'iou':
            continue
        if loss_type == 'giou':
            # calculate Ac
            yc_1 = torch.min(decoded_target[:, 0], decoded_output[:, 0])
            xc_1 = torch.min(decoded_target[:, 1], decoded_output[:, 1])
            yc_2 = torch.max(decoded_target[:, 2], decoded_output[:, 2])
            xc_2 = torch.max(decoded_target[:, 3], decoded_output[:, 3])
            Ac = (xc_2 - xc_1) * (yc_2 - yc_1)

            penalty = (Ac - U)/(Ac + eps)
        elif loss_type == 'diou':
            # central distance
            xc_target = (decoded_target[:, 3] + decoded_target[:, 1])/2
            yc_target = (decoded_target[:, 2] + decoded_target[:, 0])/2
            xc_output = (decoded_output[:, 3] + decoded_output[:, 1])/2
            yc_output = (decoded_output[:, 2] + decoded_output[:, 0])/2
            p2 = (yc_target - yc_output)**2 + (xc_target - xc_output)**2

            # diagonal of smallest enclosing box
            yc_1 = torch.min(decoded_target[:, 0], decoded_output[:, 0])
            xc_1 = torch.min(decoded_target[:, 1], decoded_output[:, 1])
            yc_2 = torch.max(decoded_target[:, 2], decoded_output[:, 2])
            xc_2 = torch.max(decoded_target[:, 3], decoded_output[:, 3])
            c2 = (xc_2 - xc_1)**2 + (yc_2 - yc_1)**2

            penalty = p2/(c2 + eps)
        elif loss_type == 'eiou':
            # central distance
            xc_target = (decoded_target[:, 3] + decoded_target[:, 1])/2
            yc_target = (decoded_target[:, 2] + decoded_target[:, 0])/2
            xc_output = (decoded_output[:, 3] + decoded_output[:, 1])/2
            yc_output = (decoded_output[:, 2] + decoded_output[:, 0])/2
            p2 = (yc_target - yc_output)**2 + (xc_target - xc_output)**2

            # enclosing box C
            yc_1 = torch.min(decoded_target[:, 0], decoded_output[:, 0])
            xc_1 = torch.min(decoded_target[:, 1], decoded_output[:, 1])
            yc_2 = torch.max(decoded_target[:, 2], decoded_output[:, 2])
            xc_2 = torch.max(decoded_target[:, 3], decoded_output[:, 3])
            wc = xc_2 - xc_1
            hc = yc_2 - yc_1

            # aspect ratio
            w_gt = decoded_target[:, 3] - decoded_target[:, 1]
            h_gt = decoded_target[:, 2] - decoded_target[:, 0]
            w_pred = decoded_output[:, 3] - decoded_output[:, 1]
            h_pred = decoded_output[:, 2] - decoded_output[:, 0]

            penalty = p2 / (wc**2 + hc**2 + eps) + (w_gt - w_pred)**2 / (wc**2 + eps) + (h_gt - h_pred)**2 / (hc**2 + eps)
        else:
            raise AssertionError('no valid iou loss')

        loss.append(1. - iou + penalty)

    loss = torch.cat(loss)
    return loss.mean()


def one_hot(x, num_classes: int):
    # NOTE: PyTorch one-hot does not handle -ve entries (no hot) like Tensorflow, so mask them out
    x_non_neg = (x >= 0).unsqueeze(-1)
    onehot = torch.zeros(x.shape + (num_classes,), device=x.device, dtype=torch.float32)
    return onehot.scatter(-1, x.unsqueeze(-1) * x_non_neg, 1) * x_non_neg


def loss_fn(
        cls_outputs: List[torch.Tensor],
        box_outputs: List[torch.Tensor],
        cls_targets: List[torch.Tensor],
        box_targets: List[torch.Tensor],
        num_positives: torch.Tensor,
        box_loss_type: str,
        num_classes: int,
        alpha: float,
        gamma: float,
        delta: float,
        box_loss_weight: float,
        anchors: torch.Tensor,
        label_smoothing: float = 0.,
        legacy_focal: bool = False,
        ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Computes total detection loss.
    Computes total detection loss including box and class loss from all levels.
    Args:
        cls_outputs: a List with values representing logits in [batch_size, height, width, num_anchors].
            at each feature level (index)

        box_outputs: a List with values representing box regression targets in
            [batch_size, height, width, num_anchors * 4] at each feature level (index)

        cls_targets: groundtruth class targets.

        box_targets: groundtrusth box targets.

        num_positives: num positive grountruth anchors

    Returns:
        total_loss: an integer tensor representing total loss reducing from class and box losses from all levels.

        cls_loss: an integer tensor representing total class loss.

        box_loss: an integer tensor representing total box regression loss.
    """
    # Sum all positives in a batch for normalization and avoid zero
    # num_positives_sum, which would lead to inf loss during training
    num_positives_sum = (num_positives.sum() + 1.0).float()
    levels = len(cls_outputs)

    cls_losses = []
    box_losses = []
    for l in range(levels):
        cls_targets_at_level = cls_targets[l]
        box_targets_at_level = box_targets[l]

        # Onehot encoding for classification labels.
        cls_targets_at_level_oh = one_hot(cls_targets_at_level, num_classes)

        bs, height, width, _, _ = cls_targets_at_level_oh.shape
        cls_targets_at_level_oh = cls_targets_at_level_oh.view(bs, height, width, -1)
        cls_outputs_at_level = cls_outputs[l].permute(0, 2, 3, 1).float()
        if legacy_focal:
            cls_loss = focal_loss_legacy(
                cls_outputs_at_level, cls_targets_at_level_oh,
                alpha=alpha, gamma=gamma, normalizer=num_positives_sum)
        else:
            cls_loss = new_focal_loss(
                cls_outputs_at_level, cls_targets_at_level_oh,
                alpha=alpha, gamma=gamma, normalizer=num_positives_sum, label_smoothing=label_smoothing)
        cls_loss = cls_loss.view(bs, height, width, -1, num_classes)
        cls_loss = cls_loss * (cls_targets_at_level != -2).unsqueeze(-1)
        cls_losses.append(cls_loss.sum())   # FIXME reference code added a clamp here at some point ...clamp(0, 2))

    batch_size = box_outputs[0].shape[0]
    _box_outputs = torch.concat([z.permute(0, 2, 3, 1).reshape([batch_size, -1, 4]) for z in box_outputs], dim=1)
    _box_targets = torch.concat([z.reshape([batch_size, -1, 4]) for z in box_targets], dim=1)
    box_loss = _box_loss(_box_outputs, _box_targets, anchors, num_positives_sum, loss_type=box_loss_type)

    # Sum per level losses to total loss.
    cls_loss = torch.sum(torch.stack(cls_losses, dim=-1), dim=-1)
    # box_loss = torch.sum(torch.stack(box_losses, dim=-1), dim=-1)
    total_loss = cls_loss + box_loss_weight * box_loss
    return total_loss, cls_loss, box_loss


loss_jit = torch.jit.script(loss_fn)


class DetectionLoss(nn.Module):

    __constants__ = ['num_classes']

    def __init__(self, config, anchors):
        super(DetectionLoss, self).__init__()
        self.config = config
        self.num_classes = config.num_classes
        self.alpha = config.alpha
        self.gamma = config.gamma
        self.delta = config.delta
        self.box_loss_weight = config.box_loss_weight
        self.label_smoothing = config.label_smoothing
        self.legacy_focal = config.legacy_focal
        self.use_jit = config.jit_loss
        self.anchors = anchors

    def forward(
            self,
            cls_outputs: List[torch.Tensor],
            box_outputs: List[torch.Tensor],
            cls_targets: List[torch.Tensor],
            box_targets: List[torch.Tensor],
            num_positives: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:

        l_fn = loss_fn
        if not torch.jit.is_scripting() and self.use_jit:
            # This branch only active if parent / bench itself isn't being scripted
            # NOTE: I haven't figured out what to do here wrt to tracing, is it an issue?
            l_fn = loss_jit

        return l_fn(
            cls_outputs, box_outputs, cls_targets, box_targets, num_positives, box_loss_type=self.config.box_loss_type,
            num_classes=self.num_classes, alpha=self.alpha, gamma=self.gamma, delta=self.delta,
            box_loss_weight=self.box_loss_weight, label_smoothing=self.label_smoothing, legacy_focal=self.legacy_focal, anchors=self.anchors)
