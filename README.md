# Local Photos Integration for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]
[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]
[![Buy me a coffee][buymecoffeebadge]][buymecoffee]

Display photos from your local storage on Home Assistant dashboards. Point the integration at a directory, pick an album, and it creates a camera entity you can drop into any card or use as a screensaver.

Each album exposes the following entities:

- **Camera** — the current photo, processed and served at your chosen aspect ratio and crop mode
- **Sensors** — filename, creation timestamp, and media count for the active image
- **Selects** — image selection mode, crop mode, update interval, and aspect ratio

![example][exampleimg]

## Installation

### HACS Custom Repository (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. Add this repository as a custom repository in HACS:
   - Go to HACS > Integrations > Three dots in the top right > Custom repositories
   - Add `https://github.com/migz93/ha-local_photos` with category "Integration"
3. Click "Install" on the Local Photos integration.
4. Restart Home Assistant.

### Manual Installation

1. Download the latest release from the [GitHub repository](https://github.com/migz93/ha-local_photos).
2. Extract the contents.
3. Copy the `custom_components/local_photos` folder to your Home Assistant's `custom_components` directory.
4. Restart Home Assistant.

## Configuration

### Setting Up Your Photo Directory

Create a directory for your photos and add your images to it. You can manage files via the File Editor add-on or SFTP/Samba. Supported formats: JPG, JPEG, PNG, GIF, BMP, WEBP, and TIFF. HEIC/HEIF and AVIF are also supported where the required system libraries are available.

Organise photos into albums by creating subdirectories. For example:

- `/config/www/images/vacation/` - For vacation photos
- `/media/Photos/family/` - For photos on a mounted media share

If you're using a network share (e.g. Samba), Home Assistant OS mounts it under `/media`. For a share called "Photos" the path would be `/media/Photos`.

### Adding the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION** and search for "Local Photos"
3. Enter the path to your photos directory
4. Select the album you want to display — choose "All Photos" to include everything in the directory
5. The album will appear as a camera entity (e.g. "Local Photos Vacation")

To add another album, add the integration again and select a different album.

## Options

| Setting | Options | Description |
| --- | --- | --- |
| **Crop mode** | Original, Crop, Combine images | How images are fitted to the display |
| **Aspect ratio** | 16:10, 16:9, 4:3, 1:1 | Target output dimensions |
| **Image selection** | Random, Alphabetical order | How the next image is picked |
| **Update interval** | 10s – 300s, Never | How often the image changes |

### Crop Modes

- **Original** — scales the image to fit, preserving its aspect ratio (may add black bars)
- **Crop** — crops the image to fill the frame exactly
- **Combine images** — when a portrait image is shown on a landscape display (or vice versa), two images of matching orientation are placed side by side if doing so reduces pixel loss compared to cropping a single image

### Service

Use the `local_photos.next_media` service to advance the image from an automation or script:

```yaml
action: local_photos.next_media
data:
  mode: Random  # or "Alphabetical order"
target:
  entity_id: camera.local_photos_myalbum
```

## Lovelace Wall Panel

You can combine this integration with the [lovelace-wallpanel](https://github.com/j-a-n/lovelace-wallpanel) (min version 4.8) extension by [j-a-n](https://github.com/j-a-n) to show your photos as a screensaver on your dashboards. For the best results set the crop mode to [Crop](#crop) or [Combine images](#combine-images).

Home Assistant Dashboard configuration yaml (raw config):
```yaml
wallpanel:
  enabled: true
  image_url: media-entity://camera.local_photos_myalbum
  cards:
    - type: markdown
      content: >
        {{states.camera.local_photos_myalbum.attributes.media_metadata.path}}
```

## Notes & Limitations

- Supported image formats: JPG, JPEG, PNG, GIF, BMP, WEBP, and TIFF. HEIC/HEIF and AVIF are supported where the required system libraries are present. Images larger than 20MB are skipped.
- The integration scans albums on setup — add new photos by restarting Home Assistant or reconfiguring the album.
- The specified photos directory must already exist; the integration will not create it.
- For best performance, keep your photo collection reasonably sized. Thousands of high-resolution photos may impact performance.

## Contributing

Contributions are welcome! Please read the [Contribution guidelines](CONTRIBUTING.md) before opening a pull request.

---

## 🤖 AI-Assisted Development

> **ℹ️ Transparency Notice**
>
> This integration was developed with assistance from AI coding agents (Claude Code and others). While the codebase follows Home Assistant Core standards and Silver Quality Scale patterns, AI-generated code may not be reviewed or tested to the same extent as manually written code.
>
> If you encounter any issues, please [open an issue](https://github.com/Migz93/ha-local_photos/issues) on GitHub.

---

## Credits

- Based on the [Google Photos integration](https://github.com/Daanoz/ha-google-photos) by [Daanoz](https://github.com/Daanoz), adapted to work with local photos
- Integration developed by [Migz93](https://github.com/migz93)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

---

[buymecoffee]: https://www.buymeacoffee.com/Migz93
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge
[commits-shield]: https://img.shields.io/github/commit-activity/y/migz93/ha-local_photos.svg?style=for-the-badge
[commits]: https://github.com/migz93/ha-local_photos/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[exampleimg]: docs/images/example.png
[license]: https://github.com/migz93/ha-local_photos/blob/main/LICENSE
[license-shield]: https://img.shields.io/github/license/migz93/ha-local_photos.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Migz93-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/migz93/ha-local_photos.svg?style=for-the-badge
[releases]: https://github.com/migz93/ha-local_photos/releases
[user_profile]: https://github.com/migz93
