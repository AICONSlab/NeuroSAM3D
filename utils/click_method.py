import edt
import numpy as np
import torch
import torch.nn.functional as F
from skimage.measure import label, regionprops


def get_next_click3D_torch_no_gt(prev_seg, img3D, threshold=170):
    """Selects prompt clicks from thresholded image (img3D) based on the previous segmentation (prev_seg).

    Args:
        prev_seg (torch.tensor): segmentation masks from previous iteration
        img3D (torch.tensor): input images
        threshold (int, optional): threshold value to apply to image for selecting point click. Defaults to 170.

    Returns:
        batch_points (list of torch.tensor): list of points to click
        batch_labels (list of torch.tensor): list of labels corresponding to the points
        NOTE: In this case, the labels are based on the thresholded image and not the ground truth.
    """

    mask_threshold = 0.5
    batch_points = []
    batch_labels = []

    pred_masks = prev_seg > mask_threshold
    likely_masks = img3D > threshold  # NOTE: Empirical threshold
    fn_masks = torch.logical_and(likely_masks, torch.logical_not(pred_masks))
    # NOTE: Given a strict/high threshold, the false positives are not going to be very useful (at least in my case)
    # fp_masks = torch.logical_and(torch.logical_not(likely_masks), pred_masks)

    for i in range(prev_seg.shape[0]):  # , desc="generate points":

        fn_points = torch.argwhere(fn_masks[i])
        point = None
        if len(fn_points) > 0:
            point = fn_points[np.random.randint(len(fn_points))]
            is_positive = True
        # if no mask is given, random click a negative point
        if point is None:
            point = torch.Tensor(
                [np.random.randint(sz) for sz in fn_masks[i].size()]
            ).to(torch.int64)
            is_positive = False
        bp = point[1:].clone().detach().reshape(1, 1, -1).to(pred_masks.device)
        bl = (
            torch.tensor(
                [
                    int(is_positive),
                ]
            )
            .reshape(1, 1)
            .to(pred_masks.device)
        )

        batch_points.append(bp)
        batch_labels.append(bl)

    return batch_points, batch_labels


def get_next_click3D_torch_no_gt_naive(prev_seg):
    """Selects prompt clicks from the area outside predicted masks based on previous segmentation (prev_seg). 

    Args:
        prev_seg (torch.tensor): segmentation masks from previous iteration

    Returns:
        batch_points (list of torch.tensor): list of points to click
        batch_labels (list of torch.tensor): list of labels corresponding to the points
        NOTE: In this case, the labels are based on the predicted masks and not the ground truth.
    """
    mask_threshold = 0.5

    batch_points = []
    batch_labels = []

    pred_masks = prev_seg > mask_threshold
    uncertain_masks = torch.logical_xor(
        pred_masks, pred_masks
    )  # init with all False

    for i in range(prev_seg.shape[0]):
        uncertain_region = torch.logical_or(uncertain_masks[i, 0], pred_masks[i, 0])
        points = torch.argwhere(uncertain_region) # select outside of pred mask

        if len(points) > 0:
            point = points[np.random.randint(len(points))]
            is_positive = pred_masks[i, 0, point[1], point[2], point[3]]

            bp = point[1:].clone().detach().reshape(1, 1, 3)
            bl = torch.tensor([int(is_positive)], dtype=torch.long).reshape(1, 1)
            batch_points.append(bp)
            batch_labels.append(bl)
        else:
            point = torch.Tensor(
                [np.random.randint(sz) for sz in pred_masks[i, 0].size()]
            ).to(torch.int64)
            is_positive = pred_masks[i, 0, point[1], point[2], point[3]]

            bp = point[1:].clone().detach().reshape(1, 1, 3)
            bl = torch.tensor([int(is_positive)], dtype=torch.long).reshape(1, 1)
            batch_points.append(bp)
            batch_labels.append(bl)

    return batch_points, batch_labels


def get_next_click3D_torch(prev_seg, gt_semantic_seg):

    mask_threshold = 0.5

    batch_points = []
    batch_labels = []
    # dice_list = []

    pred_masks = prev_seg > mask_threshold
    true_masks = gt_semantic_seg > 0
    fn_masks = torch.logical_and(true_masks, torch.logical_not(pred_masks))
    fp_masks = torch.logical_and(torch.logical_not(true_masks), pred_masks)

    for i in range(gt_semantic_seg.shape[0]):  # , desc="generate points":

        fn_points = torch.argwhere(fn_masks[i])
        fp_points = torch.argwhere(fp_masks[i])
        point = None
        if len(fn_points) > 0 and len(fp_points) > 0:
            if np.random.random() > 0.5:
                point = fn_points[np.random.randint(len(fn_points))]
                is_positive = True
            else:
                point = fp_points[np.random.randint(len(fp_points))]
                is_positive = False
        elif len(fn_points) > 0:
            point = fn_points[np.random.randint(len(fn_points))]
            is_positive = True
        elif len(fp_points) > 0:
            point = fp_points[np.random.randint(len(fp_points))]
            is_positive = False
        # if no mask is given, random click a negative point
        if point is None:
            point = torch.Tensor(
                [np.random.randint(sz) for sz in fn_masks[i].size()]
            ).to(torch.int64)
            is_positive = False
        bp = point[1:].clone().detach().reshape(1, 1, -1).to(pred_masks.device)
        bl = (
            torch.tensor(
                [
                    int(is_positive),
                ]
            )
            .reshape(1, 1)
            .to(pred_masks.device)
        )

        batch_points.append(bp)
        batch_labels.append(bl)

    return batch_points, batch_labels  # , (sum(dice_list)/len(dice_list)).item()




def get_next_click3D_torch_ritm(prev_seg, gt_semantic_seg):
    mask_threshold = 0.5

    batch_points = []
    batch_labels = []

    pred_masks = prev_seg > mask_threshold
    true_masks = gt_semantic_seg > 0
    fn_masks = torch.logical_and(true_masks, torch.logical_not(pred_masks))
    fp_masks = torch.logical_and(torch.logical_not(true_masks), pred_masks)

    fn_mask_single = F.pad(fn_masks, (1, 1, 1, 1, 1, 1), "constant", value=0).to(
        torch.uint8
    )[0, 0]
    fp_mask_single = F.pad(fp_masks, (1, 1, 1, 1, 1, 1), "constant", value=0).to(
        torch.uint8
    )[0, 0]
    fn_mask_dt = torch.tensor(
        edt.edt(fn_mask_single.cpu().numpy(), black_border=True, parallel=4)
    )[1:-1, 1:-1, 1:-1]
    fp_mask_dt = torch.tensor(
        edt.edt(fp_mask_single.cpu().numpy(), black_border=True, parallel=4)
    )[1:-1, 1:-1, 1:-1]
    fn_max_dist = torch.max(fn_mask_dt)
    fp_max_dist = torch.max(fp_mask_dt)
    is_positive = (
        fn_max_dist > fp_max_dist
    )  # the biggest area is selected to be interaction point
    dt = fn_mask_dt if is_positive else fp_mask_dt
    to_point_mask = dt > (max(fn_max_dist, fp_max_dist) / 2.0)  # use a erosion area
    to_point_mask = to_point_mask[None, None]

    for i in range(gt_semantic_seg.shape[0]):
        points = torch.argwhere(to_point_mask[i])
        point = points[np.random.randint(len(points))]
        if fn_masks[i, 0, point[1], point[2], point[3]]:
            is_positive = True
        else:
            is_positive = False

        bp = point[1:].clone().detach().reshape(1, 1, 3)
        bl = torch.tensor(
            [
                int(is_positive),
            ]
        ).reshape(1, 1)
        batch_points.append(bp)
        batch_labels.append(bl)

    return batch_points, batch_labels  # , (sum(dice_list)/len(dice_list)).item()


def get_next_click3D_torch_2(prev_seg, gt_semantic_seg):

    mask_threshold = 0.5

    pred_masks = prev_seg > mask_threshold
    true_masks = gt_semantic_seg > 0

    # get fp, fn and combine them
    fn_masks = torch.logical_and(true_masks, torch.logical_not(pred_masks))
    fp_masks = torch.logical_and(torch.logical_not(true_masks), pred_masks)
    points_to_select = torch.logical_or(fn_masks, fp_masks)

    # get the indices of the points
    error_indices = torch.argwhere(points_to_select)

    # shuffle the indices
    error_indices = error_indices[torch.randperm(error_indices.shape[0])]

    # get the batch indices of the points
    batch_indices = error_indices[:, 0]

    # get a unique point per batch
    unique: torch.Tensor
    inverse: torch.Tensor
    unique, inverse = torch.unique(batch_indices, sorted=True, return_inverse=True)
    perm = torch.arange(inverse.size(0), dtype=inverse.dtype, device=inverse.device)
    # inverse, perm = inverse.flip([0]), perm.flip([0])
    perm = inverse.new_empty((unique.size(0),)).scatter_(0, inverse, perm)

    batched_points = error_indices[perm]

    # get the labels
    batched_labels = fn_masks[tuple(batched_points.t())].int()
    batched_labels = batched_labels.unsqueeze(1)

    # convert to right shape
    batched_points = batched_points[:, 2:].unsqueeze(1)

    return batched_points, batched_labels


def get_next_click3D_torch_largest_blob(prev_seg: torch.Tensor, gt_semantic_seg: torch.Tensor):
    mask_threshold = 0.5

    batch_points = []
    batch_labels = []

    pred_masks = prev_seg > mask_threshold
    true_masks = gt_semantic_seg > 0
    fn_masks = torch.logical_and(true_masks, torch.logical_not(pred_masks))
    fp_masks = torch.logical_and(torch.logical_not(true_masks), pred_masks)

    for i in range(gt_semantic_seg.shape[0]):
        blobs = label(true_masks[i, 0].cpu().detach().numpy())
        blobs_props = regionprops(blobs)
        largest_blob = None
        largest_blob_size = 0
        for prop in blobs_props:
            if prop.area > largest_blob_size:
                largest_blob = prop
                largest_blob_size = prop.area
        
        if largest_blob is None:
            print("No blobs found")
            continue

        img_label = largest_blob.label

        possible_points = np.argwhere(blobs == img_label)
        point = possible_points[np.random.randint(len(possible_points))]

        bp = torch.tensor(point).reshape(1,1,3).to(prev_seg.device)
        bl = torch.tensor([1,]).reshape(1,1).to(prev_seg.device)
        batch_points.append(bp)
        batch_labels.append(bl)

    return batch_points, batch_labels
