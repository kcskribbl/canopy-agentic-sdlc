package dev.canopy.links;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "docs.enabled", havingValue = "true")
class ApiDocs implements WebMvcConfigurer {
    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        registry.addResourceHandler("/docs/assets/**")
                .addResourceLocations("classpath:/META-INF/resources/webjars/swagger-ui/5.36.0/");
        registry.addResourceHandler("/docs/**").addResourceLocations("classpath:/docs/");
    }
}
