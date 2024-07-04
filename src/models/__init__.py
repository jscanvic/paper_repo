from deepinv.models import SwinIR
from torch import nn
from torch.nn.parallel import DataParallel
from torch.nn import Module

# NOTE: The file structure should be way simpler.
from .convolutional import ConvNeuralNetwork
from .pnp import PnPModel
from .dip import DeepImagePrior
from .bm3d_deblurring import BM3D
from .upsample import Upsample
from .diffpir import DiffPIR
from .dps import DPS
from .tv import TV


# NOTE: This should not exist!
class Identity(Module):
    def forward(self, y):
        return y


# NOTE: This should ideally be a method of the model itself with an
# accompanying function to load the weights back in.
def get_model_state_dict(model):
    if not isinstance(model, DataParallel):
        model_state_dict = model.state_dict()
    else:
        model_state_dict = model.module.state_dict()
    return model_state_dict


# NOTE: There should be a Model class and the function get_model would return
# an instance of it.
def get_model(
    args,
    physics,
    device,
):
    task = args.task
    sr_factor = args.sr_factor
    noise_level = args.noise_level
    tv_lambd = getattr(args, "tv_lambd", None)
    tv_max_iter = getattr(args, "tv_max_iter", None)
    kind = args.model_kind

    if args.dip_iterations is not None:
        dip_iterations = args.dip_iterations
    else:
        if args.task == "deblurring" and "Gaussian" in args.kernel:
            dip_iterations = 4000
        elif args.task == "deblurring":
            dip_iterations = 1000
        elif args.task == "sr":
            dip_iterations = 1000

    data_parallel_devices = (
        args.data_parallel_devices.split(",")
        if args.data_parallel_devices is not None
        else None
    )

    if kind == "swinir":
        upscale = sr_factor if task == "sr" else 1
        upsampler = "pixelshuffle" if task == "sr" else None
        model = SwinIR(
            img_size=48,
            patch_size=1,
            in_chans=3,
            embed_dim=180,
            depths=[6, 6, 6, 6, 6, 6],
            num_heads=[6, 6, 6, 6, 6, 6],
            window_size=8,
            mlp_ratio=2,
            qkv_bias=True,
            qk_scale=None,
            drop_rate=0.0,
            attn_drop_rate=0.0,
            drop_path_rate=0.1,
            norm_layer=nn.LayerNorm,
            ape=False,
            patch_norm=True,
            use_checkpoint=False,
            upscale=upscale,
            img_range=1.0,
            upsampler=upsampler,
            resi_connection="1conv",
            pretrained=None,
        )
    elif kind == "CNN":
        upsampling_rate = sr_factor if task == "sr" else 1
        unet_residual = args.unet_residual
        num_conv_blocks = args.unet_num_conv_blocks
        model = ConvNeuralNetwork(
            in_channels=3,
            upsampling_rate=upsampling_rate,
            unet_residual=unet_residual,
            num_conv_blocks=num_conv_blocks,
        )
    elif kind == "dip":
        model = DeepImagePrior(
            physics=physics, sr_factor=sr_factor, iterations=dip_iterations
        )
    elif kind == "pnp":
        noise_level_img = noise_level / 255
        early_stop = True

        model = PnPModel(
            physics,
            noise_level_img,
            early_stop=early_stop,
            device=device,
            channels=3,
        )
    elif kind == "bm3d":
        model = BM3D(physics=physics, sigma_psd=noise_level / 255)
    elif kind == "diffpir":
        model = DiffPIR(physics=physics)
    elif kind == "dps":
        model = DPS(physics=physics, device=device)
    elif kind == "tv":
        model = TV(physics=physics, lambd=tv_lambd, max_iter=tv_max_iter)
    elif kind == "id":
        model = Identity()
    elif kind == "up":
        model = Upsample(factor=sr_factor)
    else:
        raise ValueError(f"Unknown model kind: {kind}")

    if data_parallel_devices is not None:
        devices = data_parallel_devices
        model = DataParallel(model, device_ids=devices, output_device=device)

    return model
