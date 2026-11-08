/*
 * zlvideo: ZenLink Linux Native Video Decoder using FFmpeg
 * Decodes H.264 / HEVC NAL units to 32-bit BGRA frames.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include <libavcodec/avcodec.h>
#include <libavutil/opt.h>
#include <libavutil/pixdesc.h>
#include <libswscale/swscale.h>

typedef struct ZlVideo {
    AVCodecContext *ctx;
    AVPacket *pkt;
    AVFrame *frame;
    struct SwsContext *sws;
    int sws_w, sws_h, sws_fmt;
    uint8_t *bgra_buf;
    int bgra_cap;
} ZlVideo;

int zl_video_codec_available(int is_hevc)
{
    enum AVCodecID id = is_hevc ? AV_CODEC_ID_HEVC : AV_CODEC_ID_H264;
    return avcodec_find_decoder(id) != NULL ? 1 : 0;
}

void zl_video_close(ZlVideo *v)
{
    if (!v)
        return;
    if (v->sws)
        sws_freeContext(v->sws);
    if (v->bgra_buf)
        free(v->bgra_buf);
    av_frame_free(&v->frame);
    av_packet_free(&v->pkt);
    avcodec_free_context(&v->ctx);
    free(v);
}

ZlVideo *zl_video_open(int is_hevc)
{
    enum AVCodecID id = is_hevc ? AV_CODEC_ID_HEVC : AV_CODEC_ID_H264;
    const AVCodec *codec = avcodec_find_decoder(id);
    if (!codec)
        return NULL;

    ZlVideo *v = calloc(1, sizeof(*v));
    if (!v)
        return NULL;

    v->ctx = avcodec_alloc_context3(codec);
    v->pkt = av_packet_alloc();
    v->frame = av_frame_alloc();
    if (!v->ctx || !v->pkt || !v->frame)
        goto fail;

    v->ctx->thread_count = 0; // multi-threaded decoding
    v->ctx->flags |= AV_CODEC_FLAG_LOW_DELAY;
    v->ctx->flags2 |= AV_CODEC_FLAG2_FAST;

    if (avcodec_open2(v->ctx, codec, NULL) < 0)
        goto fail;

    return v;

fail:
    zl_video_close(v);
    return NULL;
}

int zl_video_decode(ZlVideo *v, const uint8_t *data, int len, uint8_t **out_bgra, int *out_w, int *out_h)
{
    int ret;
    if (!v || !data || len <= 0 || !out_bgra || !out_w || !out_h)
        return -1;

    if (av_new_packet(v->pkt, len) < 0)
        return -1;
    memcpy(v->pkt->data, data, len);

    ret = avcodec_send_packet(v->ctx, v->pkt);
    av_packet_unref(v->pkt);
    if (ret < 0 && ret != AVERROR(EAGAIN))
        return -1;

    ret = avcodec_receive_frame(v->ctx, v->frame);
    if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF)
        return 0; // needs more data
    if (ret < 0)
        return -1;

    int w = v->frame->width;
    int h = v->frame->height;
    int fmt = v->frame->format;

    if (!v->sws || v->sws_w != w || v->sws_h != h || v->sws_fmt != fmt) {
        if (v->sws)
            sws_freeContext(v->sws);
        v->sws = sws_getContext(w, h, (enum AVPixelFormat)fmt,
                                w, h, AV_PIX_FMT_BGRA,
                                SWS_FAST_BILINEAR, NULL, NULL, NULL);
        if (!v->sws) {
            av_frame_unref(v->frame);
            return -1;
        }
        v->sws_w = w;
        v->sws_h = h;
        v->sws_fmt = fmt;
    }

    int needed = w * h * 4;
    if (needed > v->bgra_cap) {
        free(v->bgra_buf);
        v->bgra_buf = malloc(needed);
        if (!v->bgra_buf) {
            v->bgra_cap = 0;
            av_frame_unref(v->frame);
            return -1;
        }
        v->bgra_cap = needed;
    }

    uint8_t *dst[4] = { v->bgra_buf, NULL, NULL, NULL };
    int dst_linesize[4] = { w * 4, 0, 0, 0 };

    sws_scale(v->sws, (const uint8_t * const *)v->frame->data, v->frame->linesize,
              0, h, dst, dst_linesize);

    av_frame_unref(v->frame);

    *out_bgra = v->bgra_buf;
    *out_w = w;
    *out_h = h;
    return 1;
}
