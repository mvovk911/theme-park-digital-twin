"""Explicit external previews. These routes never write the synthetic backbone."""
from fastapi import HTTPException, Query
from .weather import WeatherPreview, WeatherError


def install_integration_routes(app):
    weather = WeatherPreview()
    app.state.weather_preview = weather

    @app.get("/api/integrations/weather/preview")
    def preview_weather(latitude: float = Query(..., ge=-90, le=90),
                        longitude: float = Query(..., ge=-180, le=180)):
        try:
            return weather.preview(latitude, longitude)
        except WeatherError as exc:
            raise HTTPException(502, {"code": "weather_preview_invalid", "message": str(exc)}) from None
        except Exception:
            # Provider errors may contain transport configuration. Do not echo them.
            raise HTTPException(502, {"code": "weather_preview_unavailable", "message": "External weather is unavailable; synthetic park values are unchanged."}) from None
