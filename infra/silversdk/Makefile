
schemas/schema.1.json:
	. env/bin/activate && dotenv run \
		http GET \
			http://localhost:8080/swagger/schema/ \
			'Authorization: Token $(SILVER_AUTH_TOKEN)' > $@
