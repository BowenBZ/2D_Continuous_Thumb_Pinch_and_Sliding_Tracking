'''
This script is used to segment the hand from the video stream with the skin color and track the touch position

It includes:
1. Use Otsu threshold to segment the hand part
2. Use Convexity Defects to get touch point
3. Draw the movements in a drawing board
'''


def threshold_masking(bgr_img):
    """Get the mask for the bgr_img
    1. Use Otsu thresholding
    2. Erode and dilate to remove noise
    3. Get the area with the max contour 

    Arguments:
        bgr_img {np.array} -- [BGR Image]

    Returns:
        mask [np.array] -- [0/255 Mask]
        max_contour [3-d array] -- [The contour of the mask] 
        masked_image [np.array] -- [Adopt the mask to the input bgr image]
    """
    # Convert to YCrCb
    img_ycrcb = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2YCR_CB)

    # Otsu Thresholding
    _, mask = cv2.threshold(img_ycrcb[:, :, 1], 0, 255,
                            cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Erode or dilate the edges that has been removed
    kernel_size = min(bgr_img.shape[0], bgr_img.shape[1]) // 50
    element = cv2.getStructuringElement(cv2.MORPH_RECT,
                                        (kernel_size, kernel_size))
    mask = cv2.erode(mask, element)
    mask = cv2.dilate(mask, element)

    # Get the all contours, CHAIN_APPROX_NONE means get all the points
    _, contours, _ = cv2.findContours(mask, cv2.RETR_CCOMP,
                                      cv2.CHAIN_APPROX_NONE)
    max_contour = None

    # Get the contour with max area
    if len(contours) > 0:
        max_index = 0
        max_val = -1
        for idx, c in enumerate(contours):
            if cv2.contourArea(c) > max_val:
                max_val = cv2.contourArea(c)
                max_index = idx

        max_contour = contours[max_index]

        # Draw the max contours area and fill it
        canvas = np.zeros(mask.shape).astype('uint8')
        mask = cv2.drawContours(canvas, contours, max_index, 255, -1)

    masked_image = cv2.bitwise_and(bgr_img, bgr_img, mask=mask)

    return mask, max_contour, masked_image


import cv2
import numpy as np

if __name__ == '__main__':
    from time import sleep
    import picamera_control
    import sys, traceback
    from draw_tools import draw_vertical_lines
    
    """
    This function get the frame from the camera, and use thresholding to segment the hand part
    """
    try:
        camera, rawCapture = picamera_control.configure_camera(640,
                                                               480,
                                                               FRAME_RATE=35)

        for frame in camera.capture_continuous(rawCapture,
                                               format="bgr",
                                               use_video_port=True):
            bgr_image = frame.array

            # img_ycrcb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2YCR_CB)
            # cv2.imshow("Y", img_ycrcb[:,:,0])
            # cv2.imshow("Cr", img_ycrcb[:,:,1])
            # cv2.imshow("Cb", img_ycrcb[:,:,2])

            # Get the mask using the Otsu thresholding method
            mask, max_contour, segment = threshold_masking(bgr_image)

            # Draw contours
            cv2.drawContours(segment, [max_contour],
                             0, [0, 0, 255],
                             thickness=3)

            # Display
            image_joint = np.concatenate((bgr_image, segment), axis=1)
            draw_vertical_lines(image_joint, 1)
            cv2.imshow('Image', image_joint)
            cv2.imshow('Mask', mask)

            # if the user pressed ESC, then stop looping
            keypress = cv2.waitKey(25) & 0xFF
            if keypress == 27:
                break

            rawCapture.truncate(0)

        camera.close()
        cv2.destroyAllWindows()
    except Exception as e:
        camera.close()
        cv2.destroyAllWindows()
        print("Exception in user code:")
        print('-' * 60)
        traceback.print_exc(file=sys.stdout)
        print('-' * 60)
