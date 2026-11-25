FROM eclipse-temurin:21-jre
WORKDIR /app
RUN mkdir -p /app/data && chown 10001:10001 /app/data
COPY --chown=10001:10001 target/links-service-1.0.0.jar /app/links.jar
USER 10001:10001
ENV BIND_ADDRESS=0.0.0.0
EXPOSE 8080
ENTRYPOINT ["java","-jar","/app/links.jar"]
