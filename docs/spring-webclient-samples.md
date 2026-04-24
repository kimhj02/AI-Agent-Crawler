# Spring WebClient 연동 샘플 (Python API v1)

아래 코드는 Python 서버(`FastAPI`)를 Spring Boot에서 호출하기 위한 최소 샘플입니다.

- Base URL 예시: `http://python-service:8000`
- 공통 응답 포맷:
  - 성공: `{"success": true, "data": ...}`
  - 실패: `{"success": false, "code": "...", "msg": "..."}`

## 1) 공통 DTO

```java
package com.example.python.dto;

public record ApiSuccessResponse<T>(
    boolean success,
    T data
) {}
```

```java
package com.example.python.dto;

public record ApiErrorResponse(
    boolean success,
    String code,
    String msg
) {}
```

---

## 2) 식단 크롤링 (`POST /api/v1/python/meals/crawl`)

```java
package com.example.python.dto;

import java.time.LocalDate;
import java.util.List;

public record MealsCrawlRequest(
    String schoolName,
    String cafeteriaName,
    String sourceUrl,
    LocalDate startDate,
    LocalDate endDate
) {}

public record MealsCrawlResponse(
    String schoolName,
    String cafeteriaName,
    String sourceUrl,
    String startDate,
    String endDate,
    List<DailyMeal> meals
) {
    public record DailyMeal(
        String mealDate,
        String mealType,
        List<MenuItem> menus
    ) {}

    public record MenuItem(
        String cornerName,
        Integer displayOrder,
        String menuName
    ) {}
}
```

---

## 3) 메뉴 분석 (`POST /api/v1/python/menus/analyze`)

```java
package com.example.python.dto;

import java.util.List;

public record MenuAnalyzeRequest(
    List<MenuTarget> menus
) {
    public record MenuTarget(
        Long menuId,
        String menuName
    ) {}
}

public record MenuAnalyzeResponse(
    List<ResultItem> results
) {
    public record ResultItem(
        Long menuId,
        String menuName,
        String status,
        String reason,
        String modelName,
        String modelVersion,
        String analyzedAt,
        List<IngredientItem> ingredients
    ) {}

    public record IngredientItem(
        String ingredientCode,
        Double confidence
    ) {}
}
```

---

## 4) 메뉴 번역 (`POST /api/v1/python/menus/translate`)

```java
package com.example.python.dto;

import java.util.List;

public record MenuTranslateRequest(
    List<MenuTarget> menus,
    List<String> targetLanguages
) {
    public record MenuTarget(
        Long menuId,
        String menuName
    ) {}
}

public record MenuTranslateResponse(
    List<ResultItem> results
) {
    public record ResultItem(
        Long menuId,
        String sourceName,
        List<TranslationItem> translations,
        List<TranslationErrorItem> translationErrors
    ) {}

    public record TranslationItem(
        String langCode,
        String translatedName
    ) {}

    public record TranslationErrorItem(
        String langCode,
        String reason
    ) {}
}
```

---

## 5) WebClient Service 샘플

```java
package com.example.python;

import com.example.python.dto.*;
import lombok.RequiredArgsConstructor;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
@RequiredArgsConstructor
public class PythonApiClient {

    private final WebClient pythonWebClient;

    public MealsCrawlResponse crawlMeals(MealsCrawlRequest request) {
        var type = new ParameterizedTypeReference<ApiSuccessResponse<MealsCrawlResponse>>() {};
        return pythonWebClient.post()
            .uri("/api/v1/python/meals/crawl")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(type)
            .map(ApiSuccessResponse::data)
            .block();
    }

    public MenuAnalyzeResponse analyzeMenus(MenuAnalyzeRequest request) {
        var type = new ParameterizedTypeReference<ApiSuccessResponse<MenuAnalyzeResponse>>() {};
        return pythonWebClient.post()
            .uri("/api/v1/python/menus/analyze")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(type)
            .map(ApiSuccessResponse::data)
            .block();
    }

    public MenuTranslateResponse translateMenus(MenuTranslateRequest request) {
        var type = new ParameterizedTypeReference<ApiSuccessResponse<MenuTranslateResponse>>() {};
        return pythonWebClient.post()
            .uri("/api/v1/python/menus/translate")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(request)
            .retrieve()
            .bodyToMono(type)
            .map(ApiSuccessResponse::data)
            .block();
    }
}
```

---

## 6) WebClient Bean 설정 샘플

```java
package com.example.python;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class PythonWebClientConfig {

    @Bean
    public WebClient pythonWebClient(@Value("${python.api.base-url}") String baseUrl) {
        return WebClient.builder()
            .baseUrl(baseUrl)
            .build();
    }
}
```

`application.yml`:

```yaml
python:
  api:
    base-url: http://python-service:8000
```

